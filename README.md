# NAW — Nix-Agent-Workspace

NAW 提供两套独立能力：项目中的 Agent Workspace，以及由 Home Manager 管理的全局 Skill。
两者共用一个 Nix Skill 构建函数，但不共用安装流程。技能来源会复制到只读 Nix Store，
不检查 `SKILL.md`、名称、frontmatter 或正文。

## 项目 Workspace

```bash
nix flake new -t github:SpreadZhao/NAW#workspace my-project
cd my-project
# 编辑 flake.nix；未提交的文件使用 path: 引用。
nix develop path:$PWD
```

```nix
{
  inputs.naw.url = "github:SpreadZhao/NAW";
  inputs.my-skills = {
    url = "github:example/skills";
    flake = false;
  };
  outputs = { naw, my-skills, ... }:
    naw.lib.mkWorkspace {
      skills.example = "${my-skills}/skills/example";
      targets = [ "agents" "claude" ];
      instructions = ''
        项目的指令正文。
      '';
      packages = pkgs: [ pkgs.git pkgs.ripgrep ];
    };
}
```

`lib.mkWorkspace` 输出 `devShells.<system>.default` 和 `checks.<system>.workspace`。
进入 shell 时，Bash 安装器向上寻找最近的 `flake.nix` 作为项目根目录，
安装成功后设置 `NAW_WORKSPACE_ROOT` 并执行 `shellHook`。

| 参数 | 默认值 |
| --- | --- |
| `skills` | `{}`，名称直接映射到来源 |
| `targets` | `[ "agents" ]`；可选 `agents`、`claude`、`codex` |
| `instructions` | `""`，原样生成 `AGENTS.md` |
| `packages` | `pkgs: []`，也接受包列表 |
| `shellHook` | `""`，安装成功后执行 |
| `systems` | `[ "x86_64-linux" "aarch64-linux" ]` |

项目始终生成 `AGENTS.md`；选择 `claude` 时增加 `CLAUDE.md → AGENTS.md`。
技能目录整体链接到只读 Store。初次安装遇到已有目标就报错，包括空目录、相同链接和断链。
所有冲突先检查，任一冲突都会中止安装，不覆盖、不跳过、不接管。

未修改的受管理链接可以重复加载。更新 Nix 声明后重新进入环境即可更新技能和指令；
撤选的目标会移除，缺失的受管理链接会重建，被替换的链接会报错。
未启用的其他 Agent 目录不检查；已有父目录必须是真实目录，不能是软链。

项目状态仅位于 `.naw/`：`current` 指向当前生成版本，`roots/` 保存 Nix GC root。
安装器使用目录锁和原子版本切换，普通失败会撤销本次准备；不提供断电或强制终止后的自动修复。
内部命令名为 `naw-workspace-activate`，通常由 devShell 自动调用。

## 全局 Skill

```nix
imports = [ inputs.naw.homeManagerModules.globalSkills ];

programs.naw.globalSkills = {
  enable = true;
  skills.example = "${inputs.my-skills}/skills/example";
  targets = [ "agents" "claude" ];
};
```

全局模块只提供 `enable`、`skills` 和 `targets`。它通过 Home Manager 的 `home.file`
把每个目标目录整体链接到 Skill 构建结果，不生成项目指令，不运行 Workspace 安装器，
不创建 NAW 全局状态目录或额外 GC roots。

链接的更新、移除、冲突处理和 dry-run 均遵循 Home Manager 原生机制。
NAW 不设置强制覆盖或自动备份。旧工具生成的目录需在切换前由用户备份、移走。

## 来源与管理边界

两个入口均接受本地 Nix 路径（如 `./my-skill`）、锁定的远程 input 或 Nix derivation。
来源不要放在生成的目录内。`targets` 的对应关系为：

| target | 相对项目根目录或 home 的位置 |
| --- | --- |
| `agents` | `.agents/skills` |
| `claude` | `.claude/skills` |
| `codex` | `.codex/skills` |

Workspace 和全局 Skill 的生命周期相互独立。修改技能源或 Nix 声明，
通过项目重新加载或 Home Manager 应用使其生效；不要编辑生成结果。
Gitignore、Git 配置和 index 不归 NAW 管理，模板中的 `.gitignore` 是普通项目文件。

旧版接口和状态不兼容，也不提供别名或自动迁移。先备份并移走旧生成物，再按新接口初始化；
保留技能源和指令源。Workspace 运行依赖为 Bash、coreutils、util-linux 和 Nix，
由安装器的 Nix 包提供；全局模块没有额外 Bash 安装依赖。
