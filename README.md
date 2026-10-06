# agent-workspace

通过 Nix 管理本机和项目的 agent skills。安装引擎按每个技能入口处理，
Home Manager 与 workspace 共用同一套来源、目标和冲突规则。
管理器不依赖个人技能或 `spreadconfig`。

## 使用

通过 GitHub 模板初始化 workspace：

```bash
nix flake new -t github:SpreadZhao/agent-workspace#workspace my-workspace
cd my-workspace
# 编辑 flake.nix 后进入；Git 仓库内请先跟踪模板文件，或使用 path: 引用。
nix develop path:$PWD
```

初始化只有 flake 模板和 `nix develop`。模板没有预选技能和业务工具。
内容仓库可作为普通 `flake = false` input：

```nix
{
  inputs = {
    agent-workspace.url = "github:SpreadZhao/agent-workspace";
    personal-skills = {
      url = "github:SpreadZhao/personal-skills";
      flake = false;
    };
    nixpkgs.follows = "agent-workspace/nixpkgs";
  };
  outputs = { agent-workspace, personal-skills, ... }:
    agent-workspace.lib.mkWorkspace {
      catalog = {
        leetcode-coach = { source = personal-skills; subdir = "skills/leetcode-coach"; };
      };
      skills = [ "leetcode-coach" ];
      claude = true;
      packages = pkgs: [ pkgs.git ];
    };
}
```

## 接口

`lib.mkWorkspace` 输出 `devShells.<system>.default` 和 `checks.<system>.workspace`。
`lib.mkSkillInstaller` 接受相同安装参数以及 `pkgs`、`scope`（global/workspace）
和可选绝对字符串 `root`，返回含 `bin/agent-workspace-install` 的 derivation。
它的 `passthru.bundle`、`manifest`、`validation` 可用于检查来源；不是初始化命令。

| 参数 | 默认与行为 |
| --- | --- |
| `catalog` | `{}`；名称到路径、derivation 或来源记录。也支持 `pkgs: catalog` |
| `skills` | `[]`；显式选择，重复选择去重，未知名称报错 |
| `extraSkills` | `{}`；自动选择，与 catalog 同名时报错 |
| `targets` | agents 启用；claude、codex 关闭；支持自定义目标 |
| `mode` | `"symlink"`；或 `"copy"` |
| `onConflict` | workspace `"error"`；global `"skip"`；只有这两种策略 |
| `cleanup` | workspace `true`；global `false` |
| `systems` | `[ "x86_64-linux" "aarch64-linux" ]`，仅 workspace |
| `packages` | `pkgs: []`；也接受包列表，仅 workspace |
| `shellHook` | `""`；初始化后执行，仅 workspace |
| `claude` | `false`；开启 Claude 目标预设与 `CLAUDE.md → AGENTS.md` |
| `workspaceRoot` | `null`；从当前目录向上找最近 flake.nix；可传绝对字符串 |
| `autoActivate` | `true`；进入开发环境时准备 workspace |
| `instructions` | `""`；追加到生成的 AGENTS.md |
| `manageInstructions` | workspace `true`；关闭时不创建指令文件 |
| `manageGitignore` | workspace `true`；只维护本管理器的忽略块 |

来源记录为 `{ source = ...; subdir = "..."; targets = [ "agents" ]; }`。
`subdir` 可省略；`targets` 未指定时安装到所有启用目标。
目标配置为 `{ enable = true; path = ".agents/skills"; }`。
路径必须相对安装根目录，不允许 `..` 或符号链接父目录。
显式 `targets.claude.enable = false` 可以覆盖 `claude` 的目标预设，
指令链接由 `claude` 与 `manageInstructions` 决定。

`lib.discoverSkills { source = input; subdir = "skills"; maxDepth = 100; }`
递归生成名称到来源记录的映射，遇到技能目录便停止向下递归。
发现过程读取标准 frontmatter 的 name；构建时完整验证 YAML、name 与 description。
来源加工使用 `pkgs: catalog`，无需反向引用消费仓库。

## Home Manager

导入 `agent-workspace.homeManagerModules.default`：

```nix
programs.agent-workspace = {
  enable = true;
  catalog.my-skill = { source = skillInput; subdir = "skills/my-skill"; };
  skills = [ "my-skill" ];
  targets.claude.enable = true;
  # onConflict = "skip"; cleanup = false; mode = "symlink";
};
```

模块公开 `catalog`、`skills`、`extraSkills`、`targets`、`mode`、`onConflict`、`cleanup`。
本机安装根目录为 `home.homeDirectory`；目标预设为 `.agents/skills`、
`.claude/skills` 和 `.codex/skills`。

## 所有权与冲突

父目录和技能入口缺失时创建。完全相同的结果保持不变；现有外部入口不会被接管。
真实目录、文件、指向不同来源的链接及断开的链接都可能冲突。
`error` 在所有来源、目标、指令文件及撤选操作预检通过前不写文件。
`skip` 保留冲突入口，继续安装其他缺失项，并报告跳过原因。
没有自动覆盖策略。更新锁定来源后，旧链接与新来源不同，需要移除指定旧入口再安装。

非受管理的 AGENTS.md 即使内容相同也触发指令文件冲突；
可以选择 `manageInstructions = false` 或 `onConflict = "skip"`。
`cleanup = true` 仅清理有记录且未被修改的撤选入口；修改过的内容遵循冲突策略。
复制结果包含整个技能目录，保留链接与可执行权限，并通过内容指纹检测变化。

workspace 状态固定为 `.agent-workspace/state.json`，本机状态固定为
`.local/state/agent-workspace/state.json`。使用目录锁、原子写入和间接 GC roots。
历史来源 roots 保留，以免跳过的旧入口失去来源；状态目录可随 workspace 一起移除。
支持读取 spreadconfig 的 v2 状态与旧忽略块；迁移仍遵循来源冲突规则。
移走 workspace 后重新进入会重新注册根目录中的 GC roots。

## 验证

```bash
nix flake check path:$PWD
nix develop path:$PWD -c python tests/test_install.py
```

检查覆盖安装幂等、冲突零写入、逐项跳过、多目标、复制指纹、清理、
外部入口所有权、指令开关、旧状态迁移、来源与目标校验。
另有 Nix API 检查，覆盖选择去重、未知名称、额外来源碰撞及递归发现。
