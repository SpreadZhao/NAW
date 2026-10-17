# agent-workspace

用 Nix 声明技能和项目指令，以只读目录提供给 Agent。安装与更新使用 Bash，
不需要 Python，也不解析或校验 Skill 内容。

## 使用

```bash
nix flake new -t github:SpreadZhao/agent-workspace#workspace my-project
cd my-project
# 编辑 flake.nix 后进入环境；未提交的文件使用 path: 引用。
nix develop path:$PWD
```

```nix
{
  inputs.agent-workspace.url = "github:SpreadZhao/agent-workspace";
  inputs.my-skills = {
    url = "github:example/skills";
    flake = false;
  };
  outputs = { agent-workspace, my-skills, ... }:
    agent-workspace.lib.mkWorkspace {
      skills.example = "${my-skills}/skills/example";
      targets = [ "agents" "claude" ];
      instructions = ''
        项目的指令正文。
      '';
      packages = pkgs: [ pkgs.git pkgs.ripgrep ];
    };
}
```

来源可使用本地 Nix 路径（如 `./my-skill`）、锁定的远程 input，或 Nix derivation。
Nix 将来源内容复制到 Store；来源不应放在生成的目录内。
不检查 `SKILL.md`、名称、frontmatter 或正文，内容是否可被 Agent 使用由来源维护者负责。

## 接口

`lib.mkWorkspace` 输出 `devShells.<system>.default` 和 `checks.<system>.workspace`。
进入 shell 自动安装，安装成功后设置 `AGENT_WORKSPACE_ROOT` 并执行 `shellHook`。
项目根目录是当前目录向上遇到的最近一个包含 `flake.nix` 的目录。

| 参数 | 默认值 |
| --- | --- |
| `skills` | `{}`，名称直接映射到来源 |
| `targets` | `[ "agents" ]`；可选 `agents`、`claude`、`codex` |
| `instructions` | `""`，原样写入生成的 `AGENTS.md` |
| `packages` | `pkgs: []`，也接受包列表 |
| `shellHook` | `""`，安装成功后执行 |
| `systems` | `[ "x86_64-linux" "aarch64-linux" ]` |

目标对应 `.agents/skills`、`.claude/skills`、`.codex/skills`。
这些目录整体链接到只读 Store，目录内的技能内容也只读。
项目始终生成 `AGENTS.md`；选择 `claude` 时增加 `CLAUDE.md → AGENTS.md`。

## 安装规则

- 首次安装遇到任何已有目标都会报错，包括空目录、普通文件、相同链接和断链。
  项目的已有 `AGENTS.md` 或 `CLAUDE.md` 同样报错。
- 所有冲突先检查，任一冲突都会使本次安装失败，不覆盖、不跳过、不接管。
- 已登记且未改动的链接可以重复加载；修改 Nix 声明后重新进入环境即可更新。
  被删除的受管理链接会重新生成，被替换的链接报错，撤选的目标会移除。
- 未启用的其他 Agent 目录不检查。父目录可以存在，但不能是软链。
- Gitignore、Git 配置和 index 不参与管理。模板中的 `.gitignore` 是普通项目文件。

项目状态在 `.agent-workspace/`，本机状态在 `.local/state/agent-workspace/`。
`current` 链接指向当前生成版本，`roots/` 保存 Nix GC root，安装布局保存在 Store 中。
使用目录锁串行更新；先准备新版本，再原子切换 `current`。普通失败会撤销本次准备，
不提供断电或强制终止后的自动修复框架。

## Home Manager

```nix
imports = [ inputs.agent-workspace.homeManagerModules.default ];
programs.agent-workspace = {
  enable = true;
  skills.example = "${inputs.my-skills}/skills/example";
  targets = [ "agents" "claude" ];
};
```

安装根目录为 `home.homeDirectory`。只管理技能目录，不管理 home 根目录的指令。
启用的技能目录由这个配置独占，不能同时放入手动安装或其他工具安装的技能。
Home Manager dry-run 不执行安装。

## 从旧版重新初始化

此版本不兼容旧参数和旧状态，也不提供自动迁移。
先备份旧生成物，人工移走旧的技能目标、项目指令和管理器状态，再使用新接口进入环境。
清理的是生成物，技能源和指令源应保留。不确定是否属于旧生成物时先检查，不要递归删除来源。
原来的 `catalog`、`extraSkills`、`claude` 等配置需改成上面的 `skills` 和 `targets`。

运行依赖为 Bash、coreutils、util-linux 和 Nix，由安装器的 Nix 包提供。
