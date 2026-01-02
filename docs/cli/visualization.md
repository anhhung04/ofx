# CLI Visualization & User Experience

OFX CLI provides an enhanced terminal experience using the `rich` library for beautiful, informative output.

## Visual Features

### Full-Width Tables

All table outputs now intelligently adapt to your terminal width for optimal readability:

- **`ofx project list`** - Full-width project listing
- **`ofx secret list`** - Full-width secret tables  
- **`ofx secret search`** - Full-width search results
- **`ofx asset list`** - Full-width asset collections
- **`ofx docs api`** - Full-width API documentation tables
- **`ofx doctor check`** - Full-width system health tables

### Progress Indicators

Long-running operations now display visual feedback:

#### Spinners

- **`ofx project init`** - Animated spinner during project creation and initialization
- **`ofx project sync`** - Animated spinner during sync operations
- **`ofx flow run`** - Animated spinner during workflow execution
- **`ofx asset add`** - Animated spinner during Git clone operations
- **`ofx asset sync`** - Animated spinner during Git pull/push operations

#### Progress Bars

Workflow execution includes detailed progress tracking:

```
⚙ MyWorkflow → job1, job2 ━━━━━━━━━━━━━━━━━━━━━━━━━━ 100% 0:00:10
  ↳ job1 → step1                          ━━━━━━━━━╸━━━━━━━━━ 75% 0:00:05
```

### Enhanced Messages

#### Success Panels

Commands display success messages in styled panels:

```
┌─────────────────────────────────────┐
│ ✅ Execution Success                 │
├─────────────────────────────────────┤
│ ✓ Workflow run completed             │
│   successfully                       │
│ Output: /path/to/output              │
└─────────────────────────────────────┘
```

#### Error Panels

Failures are clearly highlighted with colored borders and icons:

```
┌─────────────────────────────────────┐
│ ❌ Execution Failed                  │
├─────────────────────────────────────┤
│ Workflow run failed                  │
│ Status: failed                       │
│ Error: Connection timeout            │
└─────────────────────────────────────┘
```

#### Warning Boxes

Sensitive operations display warnings:

```
┌─────────────────────────────────────┐
│ ⚠️  WARNING                          │
├─────────────────────────────────────┤
│ Secret values are displayed above!   │
└─────────────────────────────────────┘
```

### Workflow Input Display

`ofx flow run` displays inputs in a formatted table before execution:

```
Workflow Inputs
┌─────────────┬──────────────────────┐
│ Parameter   │ Value                │
├─────────────┼──────────────────────┤
│ target      │ example.com          │
│ ports       │ 80,443,8080          │
│ timeout     │ 30                   │
└─────────────┴──────────────────────┘
```

## Consistent Styling

All tables use:
- **Cyan borders** - Clean, professional appearance
- **Colored headers** - Bold, easy to scan
- **Proper alignment** - Left for text, right for numbers
- **Smart width** - Adapts to terminal size with `expand=True`

## Examples

### Project Management

```bash
$ ofx project list

OFX Projects (3)
┌────┬─────────────────┬──────────────────────────────────┐
│ #  │ Project Name    │ Path                             │
├────┼─────────────────┼──────────────────────────────────┤
│ 1  │ client-pentest  │ /home/user/.ofx/client-pentest   │
│ 2  │ red-team-2024   │ /home/user/.ofx/red-team-2024    │
│ 3  │ webapp-audit    │ /home/user/.ofx/webapp-audit     │
└────┴─────────────────┴──────────────────────────────────┘
```

### Secret Management

```bash
$ ofx secret list

Stored Secrets (5 found)
┌──────────────────┬──────────┐
│ Name             │ Type     │
├──────────────────┼──────────┤
│ API_KEY          │ api-key  │
│ AWS_CREDENTIALS  │ json     │
│ DB_PASSWORD      │ password │
│ GITHUB_TOKEN     │ token    │
│ SSH_PRIVATE_KEY  │ string   │
└──────────────────┴──────────┘
```

### Asset Collections

```bash
$ ofx asset list

Installed Workflow Asset Collections
┌─────────┬──────────────────────────────────┬────────────────────┐
│ Name    │ Source URL                       │ Local Path         │
├─────────┼──────────────────────────────────┼────────────────────┤
│ default │ https://github.com/.../ofx-hub   │ ~/.ofx/default     │
└─────────┴──────────────────────────────────┴────────────────────┘
```

### System Health Check

```bash
$ ofx doctor check

Essential Tools
┌──────────┬────────┬─────────────┐
│ Tool     │ Status │ Details     │
├──────────┼────────┼─────────────┤
│ docker   │ ✅     │ 24.0.7      │
│ git      │ ✅     │ 2.40.1      │
│ python   │ ✅     │ 3.12.0      │
└──────────┴────────┴─────────────┘

System Health
┌──────────────┬────────┬────────────┐
│ Check        │ Status │ Details    │
├──────────────┼────────┼────────────┤
│ Disk Space   │ ✅     │ 450GB free │
│ Memory       │ ✅     │ 16GB       │
└──────────────┴────────┴────────────┘
```

## Terminal Compatibility

The visualization enhancements work best with:

- **Modern terminals** (iTerm2, Terminal.app, Windows Terminal, Alacritty)
- **Color support** (256 colors or true color)
- **Unicode support** (for box-drawing characters and emojis)

For basic terminals, OFX gracefully falls back to simpler output.
