#!/usr/bin/env bash
set -euo pipefail

die() {
	printf 'naw: %s\n' "$*" >&2
	exit 1
}
exists() { [[ -e $1 || -L $1 ]]; }

bundle=$1
state_dir=.naw
root=$(pwd -P)
while [[ ! -f $root/flake.nix ]]; do
	[[ $root != / ]] || die 'no flake.nix above the current directory'
	root=${root%/*}
	root=${root:-/}
done
state=$root/$state_dir
exec {lock_fd}<"$root"
flock -x "$lock_fd"

# Read Nix-generated manifests without sourcing writable project code.
link_target() {
	case "$1" in
	.agents/skills | .claude/skills | .codex/skills) printf '../%s/current/skills' "$state_dir" ;;
	AGENTS.md)
		printf '%s/current/AGENTS.md' "$state_dir"
		;;
	CLAUDE.md)
		printf 'AGENTS.md'
		;;
	*) die "unknown managed path: $1" ;;
	esac
}
parents_clear() {
	local path=${1%/*}
	[[ $path != "$1" ]] || return 0
	while [[ $path != . ]]; do
		[[ ! -L $root/$path ]] || die "symlinked output parent: $root/$path"
		if exists "$root/$path"; then
			[[ -d $root/$path ]] || die "output parent is not a directory: $root/$path"
		fi
		[[ $path == */* ]] || break
		path=${path%/*}
	done
}
matches() { [[ -L $root/$1 && $(readlink -- "$root/$1") == "$(link_target "$1")" ]]; }

mapfile -t wanted <"$bundle/links"
old_paths=()
old_bundle='' old_gc=''
parents_clear "$state_dir/current"
if exists "$state"; then
	[[ -L $state/current ]] || die "unrecognized state: $state; clean the old installation before initializing"
	parents_clear "$state_dir/roots/entry"
	old_bundle=$(readlink -e -- "$state/current") || die "broken current generation: $state/current"
	old_gc=$state/roots/${old_bundle##*/}
	[[ $old_bundle == /nix/store/* && $(readlink -- "$state/current") == "roots/${old_bundle##*/}" && -L $old_gc ]] ||
		die "modified current generation: $state/current"
	[[ $(readlink -- "$old_gc") == "$old_bundle" && -f $old_bundle/links ]] ||
		die "modified generation root: $old_gc"
	mapfile -t old_paths <"$old_bundle/links"
fi
declare -A owned=() desired=() observed=()
for path in "${old_paths[@]}"; do
	link_target "$path" >/dev/null
	owned["$path"]=1 observed["$path"]=1
done
for path in "${wanted[@]}"; do
	link_target "$path" >/dev/null
	desired["$path"]=1 observed["$path"]=1
done
observed["AGENTS.md"]=1 observed["CLAUDE.md"]=1
for path in "${!observed[@]}"; do
	parents_clear "$path"
	if exists "$root/$path"; then
		[[ -v owned["$path"] ]] || die "unmanaged entry exists: $root/$path"
		matches "$path" || die "managed entry was modified: $root/$path"
	fi
done
gc_root=$state/roots/${bundle##*/}
parents_clear "$state_dir/roots/entry"
gc_existed=false
if exists "$gc_root"; then
	gc_existed=true
	[[ -L $gc_root && $(readlink -- "$gc_root") == "$bundle" ]] || die "generation root conflict: $gc_root"
fi

# Roll back prepared links if setup fails before current is replaced.
created_dirs=() added=() removed=()
staging='' committed=false
make_dir() {
	if exists "$1"; then
		[[ -d $1 && ! -L $1 ]] || die "output parent changed: $1"
		return
	fi
	make_dir "${1%/*}"
	mkdir -- "$1"
	created_dirs+=("$1")
}
finish() {
	local status=$? path i
	trap - EXIT
	# A signal can arrive just after rename succeeds, before the next assignment.
	if [[ $old_bundle != "$bundle" && -L $state/current && $(readlink -- "$state/current") == "roots/${bundle##*/}" ]]; then
		committed=true
	fi
	if ! $committed; then
		for path in "${added[@]}"; do
			if matches "$path"; then rm -- "$root/$path" || true; fi
		done
		for path in "${removed[@]}"; do
			if ! exists "$root/$path"; then ln -s -- "$(link_target "$path")" "$root/$path" || true; fi
		done
		if ! $gc_existed && [[ -L $gc_root && $(readlink -- "$gc_root") == "$bundle" ]]; then
			rm -- "$gc_root" || true
		fi
	fi
	if [[ -n $staging ]]; then
		rm -f -- "$staging/current"
		rmdir -- "$staging" || true
	fi
	if ! $committed; then
		for ((i = ${#created_dirs[@]} - 1; i >= 0; i--)); do rmdir -- "${created_dirs[i]}" 2>/dev/null || true; done
	fi
	exit "$status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

make_dir "$state/roots"
# Re-register roots after a workspace has been moved.
if [[ -n $old_gc && $old_gc != "$gc_root" ]]; then
	nix-store --realise "$old_bundle" --add-root "$old_gc" --indirect >/dev/null
fi
nix-store --realise "$bundle" --add-root "$gc_root" --indirect >/dev/null
if [[ $old_bundle != "$bundle" ]]; then
	staging=$(mktemp -d "$state/.update.XXXXXX")
	ln -s -- "roots/${bundle##*/}" "$staging/current"
fi
for path in "${wanted[@]}"; do
	if ! exists "$root/$path"; then
		if [[ $path == */* ]]; then make_dir "$root/${path%/*}"; fi
		ln -s -- "$(link_target "$path")" "$root/$path"
		added+=("$path")
	else
		matches "$path" || die "managed entry changed during installation: $root/$path"
	fi
done
for path in "${old_paths[@]}"; do
	if [[ ! -v desired["$path"] ]] && exists "$root/$path"; then
		matches "$path" || die "managed entry changed during removal: $root/$path"
		rm -- "$root/$path"
		removed+=("$path")
	fi
done
if [[ -n $staging ]]; then mv -Tf -- "$staging/current" "$state/current"; fi
committed=true
if [[ -n $old_gc && $old_gc != "$gc_root" ]]; then
	rm -- "$old_gc" || printf 'naw: could not remove old GC root: %s\n' "$old_gc" >&2
fi
printf '%s\n' "$root"
