from pathlib import Path

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from ofx.settings import DEFAULT_WORKFLOWS_DIR, get_console
from ofx.utils.misc import find_workflow


class VisualizeHandler:
    def __init__(
        self,
        workflow_name: str,
        output: str = "",
        format: str = "mermaid",
    ):
        self.workflow_name = workflow_name
        self.output = output
        self.format = format
        self.console = get_console()

    def run(self) -> None:
        """Generate and display/save workflow visualization"""
        try:
            workflow_dirs = [DEFAULT_WORKFLOWS_DIR.absolute(), Path.cwd().absolute()]
            _, workflow = find_workflow(self.workflow_name, tuple(workflow_dirs))

            if not workflow:
                self.console.print(
                    f"[red]Error:[/red] Workflow '{self.workflow_name}' not found."
                )
                return

            diagram_content = self._generate_diagram(workflow.model_dump())

            if self.output:
                output_path = Path(self.output)
                if self.format == "mermaid":
                    output_path = output_path.with_suffix(".mmd")
                    output_path.write_text(diagram_content)
                    self.console.print(
                        f"[green]Workflow visualization saved to:[/green] {output_path}"
                    )
                elif self.format == "dot":
                    output_path = output_path.with_suffix(".dot")
                    output_path.write_text(diagram_content)
                    self.console.print(
                        f"[green]Workflow visualization saved to:[/green] {output_path}"
                    )
                elif self.format == "plantuml":
                    output_path = output_path.with_suffix(".puml")
                    output_path.write_text(diagram_content)
                    self.console.print(
                        f"[green]Workflow visualization saved to:[/green] {output_path}"
                    )
                elif self.format == "d2":
                    output_path = output_path.with_suffix(".d2")
                    output_path.write_text(diagram_content)
                    self.console.print(
                        f"[green]Workflow visualization saved to:[/green] {output_path}"
                    )
                elif self.format == "json":
                    output_path = output_path.with_suffix(".json")
                    output_path.write_text(diagram_content)
                    self.console.print(
                        f"[green]Workflow visualization saved to:[/green] {output_path}"
                    )
                elif self.format == "yaml":
                    output_path = output_path.with_suffix(".yaml")
                    output_path.write_text(diagram_content)
                    self.console.print(
                        f"[green]Workflow visualization saved to:[/green] {output_path}"
                    )
                else:
                    output_path = output_path.with_suffix(".dot")
                    output_path.write_text(diagram_content)
                    self.console.print(
                        f"[green]Workflow visualization saved to:[/green] {output_path}"
                    )
            else:
                self._display_workflow_console(workflow)

        except Exception as e:
            self.console.print(f"[red]Error visualizing workflow:[/red] {e}")

    def _display_workflow_console(self, workflow) -> None:
        """Display workflow as ASCII graph with job boxes and dependencies"""
        self.console.print(f"\n[bold cyan]Workflow:[/bold cyan] {workflow.name}")
        self.console.print(f"[dim]{workflow.description}[/dim]\n")

        job_deps = {}
        job_details = {}

        for job_name, job in workflow.jobs.items():
            job_deps[job_name] = []
            if hasattr(job, 'needs') and job.needs:
                if isinstance(job.needs, list):
                    job_deps[job_name] = job.needs
                elif isinstance(job.needs, str):
                    job_deps[job_name] = [job.needs]

            step_list = self._extract_step_info(job.steps)

            job_details[job_name] = {
                'name': job.name or job_name,
                'steps': len(job.steps),
                'step_list': step_list,
            }

        self._draw_simple_graph(job_deps, job_details)

    def _extract_step_info(self, steps) -> list[str]:
        """Extract displayable information from job steps"""
        step_list = []
        max_cmd_length = 40
        
        for step in steps:
            if step.name:
                step_list.append(step.name)
            elif step.run:
                cmd = step.run.replace('\n', ' ').strip()
                step_list.append(cmd[:max_cmd_length] + '...' if len(cmd) > max_cmd_length else cmd)
            elif step.script:
                step_list.append("[script]")
            elif step.uses:
                step_list.append(f"uses: {step.uses}")
            else:
                step_list.append("[step]")
        
        return step_list

    def _draw_simple_graph(self, job_deps: dict, job_details: dict) -> None:
        """Draw ASCII graph showing job execution stages and dependencies"""
        job_keys = list(job_details.keys())
        deps_relationships = [
            (dep, job_id)
            for job_id, deps in job_deps.items()
            if deps
            for dep in deps
        ]

        stages = self._find_parallel_schedule(job_keys, deps_relationships)
        terminal_max_width = 100
        
        for stage_idx, stage_jobs in enumerate(stages):
            box_width = self._calculate_box_width(len(stage_jobs), terminal_max_width)
            box_spacing = 3
            
            job_boxes, job_deps_lines = self._prepare_stage_boxes(stage_jobs, job_details, job_deps, box_width)
            max_box_height = max(len(box) for box in job_boxes)
            
            self._pad_boxes_to_height(job_boxes, max_box_height, box_width)
            self._print_stage_boxes(job_boxes, stage_jobs)
            self._print_stage_dependencies(job_deps_lines, stage_jobs, box_width, box_spacing)
            
            if stage_idx < len(stages) - 1:
                self._print_stage_connector()

    def _calculate_box_width(self, num_jobs: int, terminal_max_width: int) -> int:
        """Calculate optimal box width based on number of parallel jobs"""
        if num_jobs == 1:
            return 50
        
        box_spacing = 3
        base_indentation = 4
        available_width = terminal_max_width - base_indentation
        calculated_width = (available_width - (num_jobs - 1) * box_spacing) // num_jobs
        return min(40, calculated_width)

    def _prepare_stage_boxes(self, stage_jobs: list, job_details: dict, job_deps: dict, box_width: int) -> tuple:
        """Create job boxes and dependency lines for a stage"""
        job_boxes = []
        job_deps_lines = []
        
        for job_id in stage_jobs:
            box_lines = self._create_simple_job_box(job_id, job_details[job_id], box_width)
            job_boxes.append(box_lines)
            
            dep_line = ""
            if job_deps.get(job_id):
                deps_str = ", ".join(job_deps[job_id])
                dep_line = f"Depends on: {deps_str}"
                if len(dep_line) > box_width:
                    dep_line = dep_line[:box_width - 3] + "..."
            job_deps_lines.append(dep_line)
        
        return job_boxes, job_deps_lines

    def _pad_boxes_to_height(self, job_boxes: list, target_height: int, box_width: int) -> None:
        """Pad all boxes to the same height for alignment"""
        border_width = 2
        for box in job_boxes:
            while len(box) < target_height:
                box.append(" " * (box_width + border_width))

    def _print_stage_boxes(self, job_boxes: list, stage_jobs: list) -> None:
        """Print job boxes side by side or stacked"""
        max_height = max(len(box) for box in job_boxes)
        base_indent = "  "
        box_spacing = "   "
        
        for row_idx in range(max_height):
            row_parts = [box[row_idx] for box in job_boxes]
            if len(stage_jobs) == 1:
                self.console.print(base_indent + row_parts[0])
            else:
                self.console.print(base_indent + box_spacing.join(row_parts))

    def _print_stage_dependencies(self, job_deps_lines: list, stage_jobs: list, box_width: int, box_spacing: int) -> None:
        """Print dependency information below job boxes"""
        if len(stage_jobs) == 1:
            if job_deps_lines[0]:
                self.console.print(f"    [dim]{job_deps_lines[0]}[/dim]")
        else:
            if any(job_deps_lines):
                dep_line = "  "
                base_indent = 2
                border_width = 2
                sub_indent = 2
                
                for idx, dep_text in enumerate(job_deps_lines):
                    if dep_text:
                        current_pos = len(dep_line.replace("[dim]", "").replace("[/dim]", ""))
                        target_pos = base_indent + idx * (box_width + border_width + box_spacing) + sub_indent
                        padding = target_pos - current_pos
                        if padding > 0:
                            dep_line += " " * padding
                        dep_line += f"[dim]{dep_text}[/dim]"
                self.console.print(dep_line)

    def _print_stage_connector(self) -> None:
        """Print arrow connector between stages"""
        self.console.print("      |")
        self.console.print("      v")
        self.console.print()

    def _create_simple_job_box(self, job_id: str, job_detail: dict, width: int) -> list[str]:
        """Create ASCII box showing job name and steps"""
        lines = []
        border_padding = 2
        max_steps_to_show = 5
        
        lines.append(f"+{'-' * width}+")
        
        job_line = f"{job_id}: {job_detail['name']}"
        if len(job_line) > width - border_padding:
            job_line = job_line[:width - 5] + "..."
        padding = width - len(job_line) - border_padding
        lines.append(f"| [bold cyan]{job_line}[/bold cyan]{' ' * padding} |")
        
        lines.append(f"|{'-' * width}|")
        
        step_list = job_detail.get('step_list', [])
        if step_list:
            for idx, step_info in enumerate(step_list[:max_steps_to_show], 1):
                step_text = f"  {idx}. {step_info}"
                if len(step_text) > width - border_padding:
                    step_text = step_text[:width - 5] + "..."
                padding = width - len(step_text) - border_padding
                lines.append(f"| [dim]{step_text}[/dim]{' ' * padding} |")
            
            if len(step_list) > max_steps_to_show:
                more_text = f"  ... and {len(step_list) - max_steps_to_show} more"
                padding = width - len(more_text) - border_padding
                lines.append(f"| [dim]{more_text}[/dim]{' ' * padding} |")
        else:
            steps_line = f"  {job_detail['steps']} step{'s' if job_detail['steps'] != 1 else ''}"
            padding = width - len(steps_line) - border_padding
            lines.append(f"| [dim]{steps_line}[/dim]{' ' * padding} |")
        
        lines.append(f"+{'-' * width}+")
        
        return lines

    def _plan_workflow_stages(self, job_deps: dict, job_details: dict) -> list:
        """Organize jobs into parallel execution stages based on dependencies"""
        job_keys = list(job_details.keys())
        deps_relationships = [
            (dep, job_id)
            for job_id, deps in job_deps.items()
            if deps
            for dep in deps
        ]
        return self._find_parallel_schedule(job_keys, deps_relationships)

    def _find_parallel_schedule(self, job_keys: list, deps_relationships: list) -> list:
        """Use topological sort to group jobs into parallel execution stages"""
        from collections import deque
        
        graph = {job: [] for job in job_keys}
        indegree = dict.fromkeys(job_keys, 0)

        for dep, job in deps_relationships:
            if dep in graph and job in graph:
                graph[dep].append(job)
                indegree[job] += 1

        queue = deque([job for job in job_keys if indegree[job] == 0])
        stages = []

        while queue:
            current_stage = []
            stage_size = len(queue)
            
            for _ in range(stage_size):
                job = queue.popleft()
                current_stage.append(job)

                for dependent in graph[job]:
                    indegree[dependent] -= 1
                    if indegree[dependent] == 0:
                        queue.append(dependent)

            if current_stage:
                stages.append(current_stage)

        all_jobs_processed = sum(len(stage) for stage in stages) == len(job_keys)
        if not stages or not all_jobs_processed:
            return self._calculate_dependency_levels_as_stages(job_keys, deps_relationships)

        return stages

    def _calculate_dependency_levels_as_stages(self, job_keys: list, deps_relationships: list) -> list:
        """Calculate stages based on dependency depth when topological sort fails"""
        depends_on = {job: [] for job in job_keys}
        for dep, job in deps_relationships:
            depends_on[job].append(dep)

        levels = {}
        for job in job_keys:
            if not depends_on[job]:
                levels[job] = 0
            else:
                levels[job] = max(levels.get(dep, -1) for dep in depends_on[job]) + 1

        max_level = max(levels.values()) if levels else 0
        stages = []
        for level in range(max_level + 1):
            stage_jobs = [job for job, job_level in levels.items() if job_level == level]
            if stage_jobs:
                stages.append(stage_jobs)

        return stages

    def _render_ascii_flowchart(self, execution_stages: list, job_deps: dict, job_details: dict) -> Text:
        """Render an ASCII diagram flowchart"""
        if not execution_stages:
            return Text("[yellow]No execution stages found[/yellow]")

        diagram_lines = []
        
        H_LINE = "─"
        V_LINE = "│"
        TOP_LEFT = "┌"
        TOP_RIGHT = "┐"
        BOTTOM_LEFT = "└"
        BOTTOM_RIGHT = "┘"
        T_DOWN = "┬"
        T_UP = "┴"
        T_RIGHT = "├"
        T_LEFT = "┤"
        CROSS = "┼"
        ARROW_DOWN = "↓"
        ARROW_RIGHT = "→"
        
        max_width = 100
        
        for stage_idx, stage_jobs in enumerate(execution_stages):
            if stage_idx > 0:
                diagram_lines.append("")
            
            job_box_width = min(35, (max_width - (len(stage_jobs) - 1) * 3) // len(stage_jobs))
            
            if len(stage_jobs) == 1:
                job_id = stage_jobs[0]
                box = self._create_job_box(job_id, job_details[job_id], job_box_width)
                for line in box:
                    diagram_lines.append("    " + line)
            else:
                boxes = [self._create_job_box(jid, job_details[jid], job_box_width) for jid in stage_jobs]
                max_height = max(len(box) for box in boxes)
                
                for box in boxes:
                    while len(box) < max_height:
                        box.append(" " * job_box_width)
                
                for row_idx in range(max_height):
                    row_parts = []
                    for box in boxes:
                        row_parts.append(box[row_idx])
                    diagram_lines.append("    " + "   ".join(row_parts))
            
            if stage_idx < len(execution_stages) - 1:
                diagram_lines.append("")
                
                next_stage = execution_stages[stage_idx + 1]
                edges = self._draw_stage_connectors(
                    stage_jobs, next_stage, job_deps, job_box_width, len(stage_jobs), len(next_stage)
                )
                diagram_lines.extend(edges)
                diagram_lines.append("")
        
        return Text.from_markup("\n".join(diagram_lines))
    
    def _draw_stage_connectors(self, from_jobs: list, to_jobs: list, job_deps: dict, 
                                box_width: int, from_count: int, to_count: int) -> list[str]:
        """Draw visual connector lines between stages with modern style"""
        H_LINE = "─"
        V_LINE = "│"
        T_DOWN = "┬"
        T_UP = "┴"
        CURVE_DOWN_RIGHT = "╮"
        CURVE_DOWN_LEFT = "╭"
        ARROW_DOWN = "▼"  # Filled triangle
        DOT = "•"
        
        connector_lines = []
        
        spacing = 3
        base_indent = "    "
        
        deps_map = {}
        has_explicit_deps = False
        for from_job in from_jobs:
            deps_map[from_job] = []
            for to_job in to_jobs:
                if from_job in job_deps.get(to_job, []):
                    deps_map[from_job].append(to_job)
                    has_explicit_deps = True
        
        if not has_explicit_deps:
            if from_count == 1 and to_count == 1:
                center = base_indent + " " * (box_width // 2)
                connector_lines.append(center + f"[dim yellow]{V_LINE}[/dim yellow]")
                connector_lines.append(center + f"[yellow]{ARROW_DOWN}[/yellow]")
            elif from_count == 1 and to_count > 1:
                center = base_indent + " " * (box_width // 2)
                connector_lines.append(center + f"[dim yellow]{V_LINE}[/dim yellow]")
                connector_lines.append(center + f"[yellow]{DOT}[/yellow]")
                
                line_start = box_width // 2
                line_end = to_count * box_width + (to_count - 1) * spacing - (box_width // 2)
                line = base_indent + " " * line_start
                for i in range(line_end - line_start + 1):
                    if i == 0:
                        line += f"[yellow]{CURVE_DOWN_LEFT}[/yellow]"
                    elif i == line_end - line_start:
                        line += f"[yellow]{CURVE_DOWN_RIGHT}[/yellow]"
                    else:
                        line += f"[dim yellow]{H_LINE}[/dim yellow]"
                connector_lines.append(line)
                
                arrow_line = base_indent
                for i in range(to_count):
                    pos = i * (box_width + spacing) + box_width // 2
                    arrow_line += " " * (pos - len(arrow_line) + len(base_indent)) + f"[yellow]{ARROW_DOWN}[/yellow]"
                connector_lines.append(arrow_line)
            elif from_count > 1 and to_count == 1:
                arrow_line = base_indent
                for i in range(from_count):
                    pos = i * (box_width + spacing) + box_width // 2
                    arrow_line += " " * (pos - len(arrow_line) + len(base_indent)) + f"[dim yellow]{V_LINE}[/dim yellow]"
                connector_lines.append(arrow_line)
                
                line_start = box_width // 2
                line_end = from_count * box_width + (from_count - 1) * spacing - (box_width // 2)
                line = base_indent + " " * line_start
                for i in range(line_end - line_start + 1):
                    if i == 0:
                        line += f"[yellow]{CURVE_DOWN_RIGHT}[/yellow]"
                    elif i == line_end - line_start:
                        line += f"[yellow]{CURVE_DOWN_LEFT}[/yellow]"
                    else:
                        line += f"[dim yellow]{H_LINE}[/dim yellow]"
                connector_lines.append(line)
                
                center = base_indent + " " * (box_width // 2)
                connector_lines.append(center + f"[yellow]{ARROW_DOWN}[/yellow]")
            else:
                arrow_line = base_indent
                for i in range(from_count):
                    pos = i * (box_width + spacing) + box_width // 2
                    arrow_line += " " * (pos - len(arrow_line) + len(base_indent)) + f"[dim yellow]{V_LINE}[/dim yellow]"
                connector_lines.append(arrow_line)
                
                arrow_line2 = base_indent
                for i in range(from_count):
                    pos = i * (box_width + spacing) + box_width // 2
                    arrow_line2 += " " * (pos - len(arrow_line2) + len(base_indent)) + f"[yellow]{ARROW_DOWN}[/yellow]"
                connector_lines.append(arrow_line2)
        else:
            line1 = base_indent
            for from_idx, from_job in enumerate(from_jobs):
                if deps_map[from_job]:
                    from_center = from_idx * (box_width + spacing) + box_width // 2
                    line1 += " " * (from_center - len(line1) + len(base_indent)) + f"[dim cyan]{V_LINE}[/dim cyan]"
            
            if line1.strip():
                connector_lines.append(line1)
            
            connections = []
            for from_idx, from_job in enumerate(from_jobs):
                if deps_map[from_job]:
                    from_center = from_idx * (box_width + spacing) + box_width // 2
                    for to_job in deps_map[from_job]:
                        to_idx = to_jobs.index(to_job)
                        to_center = to_idx * (box_width + spacing) + box_width // 2
                        connections.append((from_center, to_center))
            
            if connections:
                all_positions = set()
                for from_pos, to_pos in connections:
                    all_positions.add(from_pos)
                    all_positions.add(to_pos)
                
                if len(all_positions) > 1:
                    min_pos = min(all_positions)
                    max_pos = max(all_positions)
                    
                    hline = base_indent + " " * min_pos
                    for i in range(max_pos - min_pos + 1):
                        pos = min_pos + i
                        if pos in all_positions:
                            if i == 0:
                                hline += f"[cyan]{CURVE_DOWN_RIGHT}[/cyan]"
                            elif i == max_pos - min_pos:
                                hline += f"[cyan]{CURVE_DOWN_LEFT}[/cyan]"
                            else:
                                hline += f"[cyan]{DOT}[/cyan]"
                        else:
                            hline += f"[dim cyan]{H_LINE}[/dim cyan]"
                    connector_lines.append(hline)
            
            arrow_line = base_indent
            for to_idx, to_job in enumerate(to_jobs):
                to_center = to_idx * (box_width + spacing) + box_width // 2
                has_dep = any(to_job in deps_map.get(from_job, []) for from_job in from_jobs)
                if has_dep:
                    arrow_line += " " * (to_center - len(arrow_line) + len(base_indent)) + f"[cyan]{ARROW_DOWN}[/cyan]"
            
            if arrow_line.strip():
                connector_lines.append(arrow_line)
        
        return connector_lines
    
    def _create_job_box(self, job_id: str, job_detail: dict, width: int) -> list[str]:
        """Create an ASCII box for a job with modern rounded style"""
        H_LINE = "─"
        V_LINE = "│"
        TOP_LEFT = "╭"
        TOP_RIGHT = "╮"
        BOTTOM_LEFT = "╰"
        BOTTOM_RIGHT = "╯"
        
        if job_detail['has_outputs'] and job_detail['has_hooks']:
            color = "green"
            symbol = "◆"  # Diamond
        elif job_detail['has_outputs']:
            color = "blue"
            symbol = "▸"  # Right triangle
        elif job_detail['has_hooks']:
            color = "yellow"
            symbol = "●"  # Circle
        else:
            color = "white"
            symbol = "▫"  # Square
        
        lines = []
        inner_width = width - 2
        
        lines.append(f"[{color}]{TOP_LEFT}{H_LINE * inner_width}{TOP_RIGHT}[/{color}]")
        
        job_id_text = f"{symbol} {job_id}"
        if len(job_id_text) > inner_width:
            job_id_text = job_id_text[:inner_width-3] + "..."
        padding = inner_width - len(job_id_text)
        lines.append(f"[{color}]{V_LINE}[/{color}][bold {color}]{job_id_text}{' ' * padding}[/bold {color}][{color}]{V_LINE}[/{color}]")
        
        job_name = job_detail['name']
        if len(job_name) > inner_width:
            job_name = job_name[:inner_width-3] + "..."
        padding = inner_width - len(job_name)
        lines.append(f"[{color}]{V_LINE}[/{color}][dim]{job_name}{' ' * padding}[/dim][{color}]{V_LINE}[/{color}]")
        
        lines.append(f"[{color}]{V_LINE}[dim]{H_LINE * inner_width}[/dim]{V_LINE}[/{color}]")
        
        steps_icon = "✦"
        steps_text = f"{steps_icon} {job_detail['steps']} step{'s' if job_detail['steps'] != 1 else ''}"
        padding = inner_width - len(steps_text)
        lines.append(f"[{color}]{V_LINE}[/{color}][dim]{steps_text}{' ' * padding}[/dim][{color}]{V_LINE}[/{color}]")
        
        if job_detail['has_outputs'] or job_detail['has_hooks']:
            features = []
            if job_detail['has_outputs']:
                features.append("→ Out")
            if job_detail['has_hooks']:
                features.append("↪ Hook")
            
            features_text = " ".join(features)
            if len(features_text) > inner_width:
                features_text = features_text[:inner_width-3] + "..."
            padding = inner_width - len(features_text)
            lines.append(f"[{color}]{V_LINE}[/{color}][dim italic]{features_text}{' ' * padding}[/dim italic][{color}]{V_LINE}[/{color}]")
        
        lines.append(f"[{color}]{BOTTOM_LEFT}{H_LINE * inner_width}{BOTTOM_RIGHT}[/{color}]")
        
        return lines

    def _draw_ascii_graph(self, level_jobs: dict, job_deps: dict, job_details: dict) -> list:
        """Draw a clean ASCII graph with proper formatting"""
        lines = []
        max_level = max(level_jobs.keys()) if level_jobs else 0

        if max_level == 0:
            jobs = level_jobs[0]
            lines.append("Jobs:")
            lines.append("")

            job_boxes = []
            for job in jobs:
                job_detail = job_details[job]
                job_name = job_detail['name']
                if len(job_name) > 18:
                    job_name = job_name[:15] + "..."

                box_width = max(len(job_name) + 4, len(job) + 4, 22)
                box = [
                    f"+{'-' * (box_width - 2)}+",
                    f"| {job_name}{' ' * (box_width - len(job_name) - 2)}|",
                    f"| Steps: {job_detail['steps']}{' ' * (box_width - len(str(job_detail['steps'])) - 8)}|",
                    f"+{'-' * (box_width - 2)}+"
                ]
                job_boxes.append(box)

            for i in range(len(job_boxes[0])):
                line_parts = []
                for box in job_boxes:
                    line_parts.append(box[i])
                lines.append("    ".join(line_parts))

            return lines

        lines.append("Workflow Execution Flow:")
        lines.append("")

        for level in range(max_level + 1):
            if level not in level_jobs:
                continue

            jobs = level_jobs[level]
            level_name = f"Level {level}"
            if level == 0:
                level_name += " (Start)"
            elif level == max_level:
                level_name += " (End)"

            lines.append(f"{level_name}:")
            lines.append("")

            for job in jobs:
                job_detail = job_details[job]
                job_name = job_detail['name']
                if len(job_name) > 25:
                    job_name = job_name[:22] + "..."

                lines.append(f"  [{job}] {job_name}")
                lines.append(f"    Steps: {job_detail['steps']}")

                features = []
                if job_detail['has_outputs']:
                    features.append("Outputs")
                if job_detail['has_hooks']:
                    features.append("Hooks")
                if features:
                    lines.append(f"    Features: {', '.join(features)}")

                lines.append("")

            if level < max_level and level + 1 in level_jobs:
                next_jobs = level_jobs[level + 1]
                lines.append("  Dependencies:")

                for from_job in jobs:
                    dependent_jobs = [to_job for to_job in next_jobs if from_job in job_deps.get(to_job, [])]
                    if dependent_jobs:
                        for dep_job in dependent_jobs:
                            lines.append(f"    {from_job} --> {dep_job}")

                lines.append("")

        return lines

    def _get_job_style(self, job_detail: dict) -> dict:
        """Get styling information for a job based on its characteristics"""
        if job_detail['has_outputs'] and job_detail['has_hooks']:
            return {"color": "green", "border": "green"}
        elif job_detail['has_outputs']:
            return {"color": "blue", "border": "blue"}
        elif job_detail['has_hooks']:
            return {"color": "yellow", "border": "yellow"}
        else:
            return {"color": "white", "border": "white"}

    def _display_enhanced_job_table(self, job_details: dict) -> None:
        """Display an enhanced job details table"""
        total_steps = sum(d['steps'] for d in job_details.values())
        avg_steps = total_steps / len(job_details) if job_details else 0
        jobs_with_outputs = sum(1 for d in job_details.values() if d['has_outputs'])
        jobs_with_hooks = sum(1 for d in job_details.values() if d['has_hooks'])
        
        table = Table(
            title=f"[bold red][#] Job Specifications[/bold red] [dim]({len(job_details)} jobs, {total_steps} steps total, avg {avg_steps:.1f} steps/job)[/dim]",
            show_header=True,
            header_style="bold red",
            show_lines=True,
            border_style="red"
        )

        table.add_column("[*] Job ID", style="cyan bold", no_wrap=True)
        table.add_column("Name", style="white")
        table.add_column("Steps", justify="center", style="yellow")
        table.add_column("Outputs", justify="center")
        table.add_column("Hooks", justify="center")
        table.add_column("Complexity", justify="center")

        for job_id, details in job_details.items():
            complexity = details['steps']
            if details['has_outputs']:
                complexity += 2
            if details['has_hooks']:
                complexity += 1
            
            complexity_label = "Low" if complexity <= 3 else "Med" if complexity <= 6 else "High"
            complexity_color = "green" if complexity <= 3 else "yellow" if complexity <= 6 else "red"
            
            table.add_row(
                f"[bold]{job_id}[/bold]",
                details['name'],
                str(details['steps']),
                "[green][Y][/green]" if details['has_outputs'] else "[dim][-][/dim]",
                "[green][Y][/green]" if details['has_hooks'] else "[dim][-][/dim]",
                f"[{complexity_color}]{complexity_label}[/{complexity_color}]",
            )

        self.console.print(table)
        
        summary = Text()
        summary.append("\nSummary: ", style="bold white")
        summary.append(f"Jobs with outputs: {jobs_with_outputs}/{len(job_details)} | ", style="dim")
        summary.append(f"Jobs with hooks: {jobs_with_hooks}/{len(job_details)}", style="dim")
        self.console.print(summary)

    def _display_job_steps(self, workflow) -> None:
        """Display detailed steps for each job in the workflow with recursive subworkflow support"""
        self.console.print()
        
        steps_panel = Panel(
            "[white]Detailed step-by-step breakdown with type indicators[/white]",
            title="[bold cyan][>>] Workflow Steps Hierarchy[/bold cyan]",
            border_style="cyan",
            padding=(0, 2)
        )
        self.console.print(steps_panel)
        self.console.print()

        workflow_tree = Tree(f"[>] [bold red]{workflow.name}[/bold red]", guide_style="red")

        for job_id, job in workflow.jobs.items():
            job_node = workflow_tree.add(f"[*] [bold yellow]{job_id}[/bold yellow] - {job.name or job_id}")
            job_node.add(f"[dim]{len(job.steps)} step{'s' if len(job.steps) != 1 else ''}[/dim]")

            self._add_steps_to_tree(job_node, job.steps, depth=0)

        self.console.print(workflow_tree)

    def _add_steps_to_tree(self, parent_node, steps: list, depth: int = 0, max_depth: int = 3) -> None:
        """Recursively add steps to the tree, handling subworkflows"""
        if depth >= max_depth:
            parent_node.add("🔄 [dim italic]Max recursion depth reached[/dim italic]")
            return

        for i, step in enumerate(steps, 1):
            step_prefix = f"📝 Step {i}"
            step_name = step.name

            if step.uses:
                step_node = parent_node.add(f"{step_prefix}: [bold green]{step_name}[/bold green] [dim][WORKFLOW][/dim]")
                try:
                    workflow_dirs = [DEFAULT_WORKFLOWS_DIR.absolute(), Path.cwd().absolute()]
                    _, subworkflow = find_workflow(step.uses, tuple(workflow_dirs))
                    subworkflow_node = step_node.add(f"[>] [bold cyan]{subworkflow.name}[/bold cyan] - {subworkflow.description}")

                    for sub_job_id, sub_job in subworkflow.jobs.items():
                        sub_job_node = subworkflow_node.add(f"[*] [bold yellow]{sub_job_id}[/bold yellow] - {sub_job.name or sub_job_id}")
                        sub_job_node.add(f"[dim]{len(sub_job.steps)} step{'s' if len(sub_job.steps) != 1 else ''}[/dim]")
                        self._add_steps_to_tree(sub_job_node, sub_job.steps, depth + 1, max_depth)

                except Exception as e:
                    step_node.add(f"[X] [red]Failed to load subworkflow: {e}[/red]")

            elif step.run:
                step_node = parent_node.add(f"{step_prefix}: [bold blue]{step_name}[/bold blue] [dim][CMD][/dim]")
                command = step.run.replace('\n', ' ').strip()
                if len(command) > 80:
                    command = command[:77] + "..."
                step_node.add(f"$ [dim]{command}[/dim]")

            elif step.script:
                step_node = parent_node.add(f"{step_prefix}: [bold magenta]{step_name}[/bold magenta] [dim][SCRIPT][/dim]")
                script = step.script.replace('\n', ' ').strip()
                if len(script) > 80:
                    script = script[:77] + "..."
                step_node.add(f">>> [dim]{script}[/dim]")

            else:
                step_node = parent_node.add(f"{step_prefix}: [bold red]{step_name}[/bold red] [dim][UNKNOWN][/dim]")
                step_node.add("[?] [dim]No action defined[/dim]")

    def _generate_diagram(self, workflow: dict) -> str:
        """Generate diagram format based on current format setting"""
        if self.format == "mermaid":
            return self._generate_mermaid(workflow)
        elif self.format == "dot":
            return self._generate_dot(workflow)
        elif self.format == "plantuml":
            return self._generate_plantuml(workflow)
        elif self.format == "d2":
            return self._generate_d2(workflow)
        elif self.format == "json":
            return self._generate_json(workflow)
        elif self.format == "yaml":
            return self._generate_yaml(workflow)
        else:
            return self._generate_dot(workflow)

    def _generate_mermaid(self, workflow: dict) -> str:
        """Generate Mermaid format string for the workflow"""
        lines = ["graph TD"]
        
        if "jobs" in workflow:
            for job_name, job_config in workflow["jobs"].items():
                description = job_config.get("name", job_name) if isinstance(job_config, dict) else str(job_config)
                safe_description = description.replace('"', "'").replace("[", "(").replace("]", ")")
                lines.append(f'    {job_name}["{job_name}: {safe_description}"]')
                
                if isinstance(job_config, dict) and "needs" in job_config:
                    needs = job_config["needs"]
                    if isinstance(needs, list):
                        for dep in needs:
                            lines.append(f"    {dep} --> {job_name}")
                    elif isinstance(needs, str):
                        lines.append(f"    {needs} --> {job_name}")
        
        return "\n".join(lines)

    def _generate_dot(self, workflow: dict) -> str:
        """Generate DOT format string for the workflow"""
        lines = ["digraph Workflow {", "    rankdir=TB;", "    node [shape=box];"]

        if "jobs" in workflow:
            for job_name, job_config in workflow["jobs"].items():
                description = job_config.get("name", job_name) if isinstance(job_config, dict) else str(job_config)
                lines.append(f'    "{job_name}" [label="{job_name}\\n{description}"];')

                if isinstance(job_config, dict) and "needs" in job_config:
                    needs = job_config["needs"]
                    if isinstance(needs, list):
                        for dep in needs:
                            lines.append(f'    "{dep}" -> "{job_name}";')
                    elif isinstance(needs, str):
                        lines.append(f'    "{needs}" -> "{job_name}";')

        lines.append("}")
        return "\n".join(lines)

    def _generate_plantuml(self, workflow: dict) -> str:
        """Generate PlantUML format string for the workflow"""
        lines = ["@startuml"]
        lines.append("!theme plain")
        lines.append("skinparam defaultTextAlignment center")
        lines.append("skinparam BoxPadding 10")
        lines.append("")
        
        if "jobs" in workflow:
            for job_name, job_config in workflow["jobs"].items():
                description = job_config.get("name", job_name) if isinstance(job_config, dict) else str(job_config)
                safe_description = description.replace('"', "'")
                
                steps_count = len(job_config.get("steps", [])) if isinstance(job_config, dict) else 0
                lines.append(f'rectangle "{job_name}\n{safe_description}\n({steps_count} steps)" as {job_name}')
            
            lines.append("")
            
            for job_name, job_config in workflow["jobs"].items():
                if isinstance(job_config, dict) and "needs" in job_config:
                    needs = job_config["needs"]
                    if isinstance(needs, list):
                        for dep in needs:
                            lines.append(f"{dep} --> {job_name}")
                    elif isinstance(needs, str):
                        lines.append(f"{needs} --> {job_name}")
        
        lines.append("@enduml")
        return "\n".join(lines)

    def _generate_d2(self, workflow: dict) -> str:
        """Generate D2 format string for the workflow"""
        lines = []
        
        if "jobs" in workflow:
            for job_name, job_config in workflow["jobs"].items():
                description = job_config.get("name", job_name) if isinstance(job_config, dict) else str(job_config)
                steps_count = len(job_config.get("steps", [])) if isinstance(job_config, dict) else 0
                
                lines.append(f"{job_name}: {{")
                lines.append(f"  shape: rectangle")
                lines.append(f'  label: "{job_name}\\n{description}\\n({steps_count} steps)"')
                lines.append("}")
                lines.append("")
            
            for job_name, job_config in workflow["jobs"].items():
                if isinstance(job_config, dict) and "needs" in job_config:
                    needs = job_config["needs"]
                    if isinstance(needs, list):
                        for dep in needs:
                            lines.append(f"{dep} -> {job_name}")
                    elif isinstance(needs, str):
                        lines.append(f"{needs} -> {job_name}")
        
        return "\n".join(lines)

    def _generate_json(self, workflow: dict) -> str:
        """Generate JSON format with workflow graph structure"""
        import json
        
        graph = {
            "name": workflow.get("name", "Unnamed Workflow"),
            "description": workflow.get("description", ""),
            "nodes": [],
            "edges": []
        }
        
        if "jobs" in workflow:
            for job_name, job_config in workflow["jobs"].items():
                node = {
                    "id": job_name,
                    "name": job_config.get("name", job_name) if isinstance(job_config, dict) else str(job_config),
                    "steps": len(job_config.get("steps", [])) if isinstance(job_config, dict) else 0
                }
                graph["nodes"].append(node)
                
                if isinstance(job_config, dict) and "needs" in job_config:
                    needs = job_config["needs"]
                    if isinstance(needs, list):
                        for dep in needs:
                            graph["edges"].append({"from": dep, "to": job_name})
                    elif isinstance(needs, str):
                        graph["edges"].append({"from": needs, "to": job_name})
        
        return json.dumps(graph, indent=2)

    def _generate_yaml(self, workflow: dict) -> str:
        """Generate YAML format with workflow graph structure"""
        import yaml
        
        graph = {
            "name": workflow.get("name", "Unnamed Workflow"),
            "description": workflow.get("description", ""),
            "nodes": [],
            "edges": []
        }
        
        if "jobs" in workflow:
            for job_name, job_config in workflow["jobs"].items():
                node = {
                    "id": job_name,
                    "name": job_config.get("name", job_name) if isinstance(job_config, dict) else str(job_config),
                    "steps": len(job_config.get("steps", [])) if isinstance(job_config, dict) else 0
                }
                graph["nodes"].append(node)
                
                if isinstance(job_config, dict) and "needs" in job_config:
                    needs = job_config["needs"]
                    if isinstance(needs, list):
                        for dep in needs:
                            graph["edges"].append({"from": dep, "to": job_name})
                    elif isinstance(needs, str):
                        graph["edges"].append({"from": needs, "to": job_name})
        
        return yaml.dump(graph, default_flow_style=False, sort_keys=False)

    def _calculate_dependency_levels(self, root_jobs: list, job_deps: dict) -> dict:
        """Calculate the dependency level for each job"""
        levels = {}

        for job in root_jobs:
            levels[job] = 0

        changed = True
        while changed:
            changed = False
            for job, deps in job_deps.items():
                if job not in levels:
                    if all(dep in levels for dep in deps):
                        max_dep_level = max(levels[dep] for dep in deps) if deps else -1
                        levels[job] = max_dep_level + 1
                        changed = True
                else:
                    if deps:
                        max_dep_level = max(levels[dep] for dep in deps)
                        required_level = max_dep_level + 1
                        if required_level > levels[job]:
                            levels[job] = required_level
                            changed = True

        return levels
