from pathlib import Path

from rich.columns import Columns
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

from ofx.runner.workflow import WorkflowRunner


class VisualizeHandler:
    def __init__(
        self,
        workflow_name: str,
        output: str | None = None,
        format: str = "dot",
    ):
        self.workflow_name = workflow_name
        self.output = output
        self.format = format
        self.console = Console()

    def run(self) -> None:
        """Generate and display/save workflow visualization"""
        try:
            # Load the workflow
            workflow = WorkflowRunner.find_flow(self.workflow_name)

            if not workflow:
                self.console.print(
                    f"[red]Error:[/red] Workflow '{self.workflow_name}' not found."
                )
                return

            # Generate DOT format representation
            dot_content = self._generate_dot(workflow.model_dump())

            if self.output:
                # Save to file
                output_path = Path(self.output)
                if self.format == "dot":
                    output_path = output_path.with_suffix(".dot")
                    output_path.write_text(dot_content)
                    self.console.print(
                        f"[green]Workflow visualization saved to:[/green] {output_path}"
                    )
                else:
                    # Try to use graphviz to render
                    self._render_graphviz(dot_content, output_path, self.format)
            else:
                # Display in terminal
                self._display_workflow_console(workflow)
                self.console.print("\n[dim]For DOT format output, use --output filename.dot[/dim]")

        except Exception as e:
            self.console.print(f"[red]Error visualizing workflow:[/red] {e}")

    def _display_workflow_console(self, workflow) -> None:
        """Display workflow visualization in console with beautiful Rich formatting"""
        # Display workflow header with panel
        header_text = Text()
        header_text.append("🔥 ", style="red bold")
        header_text.append(workflow.name, style="cyan bold")
        header_text.append(f"\n{workflow.description}", style="dim")

        header_panel = Panel(
            header_text,
            title="[bold blue]Workflow Overview[/bold blue]",
            border_style="blue",
            padding=(1, 2)
        )
        self.console.print(header_panel)
        self.console.print()

        # Build dependency graph
        job_deps = {}
        job_details = {}

        for job_name, job in workflow.jobs.items():
            job_deps[job_name] = []
            if hasattr(job, 'needs') and job.needs:
                if isinstance(job.needs, list):
                    job_deps[job_name] = job.needs
                elif isinstance(job.needs, str):
                    job_deps[job_name] = [job.needs]

            job_details[job_name] = {
                'name': job.name or job_name,
                'steps': len(job.steps),
                'has_outputs': bool(job.outputs),
                'has_hooks': bool(job.hooks),
            }

        # Find root jobs (no dependencies)
        root_jobs = [job for job in job_deps.keys() if not job_deps[job]]

        # Create beautiful graph-like flowchart using Rich tree
        if root_jobs:
            flowchart_title = Text("⚡ Workflow Execution Graph", style="bold magenta")
            self.console.print(flowchart_title)
            self.console.print()

            self._create_graph_flowchart(root_jobs, job_deps, job_details)
        else:
            self.console.print("[yellow]No jobs found in workflow[/yellow]")

        # Display enhanced job details table
        if job_details:
            self._display_enhanced_job_table(job_details)

        # Display steps for each job
        if workflow.jobs:
            self._display_job_steps(workflow)

        # Footer note
        self.console.print()
        self.console.print("[dim]💡 For Graphviz DOT format: --output filename.dot[/dim]")

    def _create_graph_flowchart(self, root_jobs: list, job_deps: dict, job_details: dict) -> None:
        """Create a beautiful graph-like flowchart visualization using Rich components"""
        # Use workflow planning logic to get execution stages
        execution_stages = self._plan_workflow_stages(job_deps, job_details)

        # Create beautiful Rich-based graph visualization based on execution stages
        self._draw_staged_graph(execution_stages, job_deps, job_details)

        # Add complete execution order graph
        # self._draw_execution_order_graph(execution_stages, job_deps, job_details, workflow)

    def _plan_workflow_stages(self, job_deps: dict, job_details: dict) -> list:
        """Plan workflow execution stages using the same logic as WorkflowRunner"""
        job_keys = list(job_details.keys())

        # Build dependency relationships
        deps_relationships = []
        for job_id, deps in job_deps.items():
            if deps:
                for dep in deps:
                    deps_relationships.append((dep, job_id))

        # Use the same parallel scheduling algorithm as WorkflowRunner
        stages = self._find_parallel_schedule(job_keys, deps_relationships)
        return stages

    def _find_parallel_schedule(self, job_keys: list, deps_relationships: list) -> list:
        """Find parallel execution schedule using topological sort with levels"""
        # Build adjacency list and indegree count
        graph = {job: [] for job in job_keys}
        indegree = dict.fromkeys(job_keys, 0)

        for dep, job in deps_relationships:
            if dep in graph and job in graph:
                graph[dep].append(job)
                indegree[job] += 1

        # Find jobs with no dependencies (indegree 0)
        from collections import deque
        queue = deque([job for job in job_keys if indegree[job] == 0])

        stages = []

        while queue:
            current_stage = []
            # Process all jobs in current level
            for _ in range(len(queue)):
                job = queue.popleft()
                current_stage.append(job)

                # Decrease indegree of dependent jobs
                for dependent in graph[job]:
                    indegree[dependent] -= 1
                    if indegree[dependent] == 0:
                        queue.append(dependent)

            if current_stage:
                stages.append(current_stage)

        # Check for cycles (if not all jobs were processed)
        if len(stages) == 0 or sum(len(stage) for stage in stages) != len(job_keys):
            # Fallback to simple dependency-based levels
            return self._calculate_dependency_levels_as_stages(job_keys, deps_relationships)

        return stages

    def _calculate_dependency_levels_as_stages(self, job_keys: list, deps_relationships: list) -> list:
        """Fallback method to calculate dependency levels as stages"""
        # Build reverse dependency map
        depends_on = {job: [] for job in job_keys}
        for dep, job in deps_relationships:
            depends_on[job].append(dep)

        # Calculate levels using the same logic as before
        levels = {}
        for job in job_keys:
            if not depends_on[job]:
                levels[job] = 0
            else:
                levels[job] = max(levels.get(dep, -1) for dep in depends_on[job]) + 1

        # Group by levels
        max_level = max(levels.values()) if levels else 0
        stages = []
        for level in range(max_level + 1):
            stage_jobs = [job for job, job_level in levels.items() if job_level == level]
            if stage_jobs:
                stages.append(stage_jobs)

        return stages

    def _draw_staged_graph(self, execution_stages: list, job_deps: dict, job_details: dict) -> None:
        """Draw a staged graph showing execution stages with edges between them"""
        if not execution_stages:
            self.console.print("[yellow]No execution stages found[/yellow]")
            return

        # Display each stage
        for stage_idx, stage_jobs in enumerate(execution_stages):
            # Stage header
            stage_title = Text()
            stage_title.append(f"Stage {stage_idx + 1}", style="bold cyan")
            if stage_idx == 0:
                stage_title.append(" [dim](Initial)[/dim]", style="dim italic")
            elif stage_idx == len(execution_stages) - 1:
                stage_title.append(" [dim](Final)[/dim]", style="dim italic")

            stage_panel = Panel(
                stage_title,
                title=f"[bold blue]🔄 Execution Stage {stage_idx + 1}[/bold blue]",
                border_style="blue",
                padding=(0, 1)
            )
            self.console.print(stage_panel)

            # Display jobs in this stage
            if len(stage_jobs) == 1:
                job_detail = job_details[stage_jobs[0]]
                job_panel = self._create_job_panel(stage_jobs[0], job_detail)
                self.console.print(job_panel)
            else:
                # Multiple jobs in stage - use columns
                job_panels = []
                for job_id in stage_jobs:
                    job_detail = job_details[job_id]
                    job_panel = self._create_job_panel(job_id, job_detail)
                    job_panels.append(job_panel)

                columns = Columns(job_panels, equal=True, expand=True)
                self.console.print(columns)

            # Add edges to next stage
            if stage_idx < len(execution_stages) - 1:
                next_stage = execution_stages[stage_idx + 1]
                edges = self._create_stage_edges(stage_jobs, next_stage, job_deps)

                if edges:
                    edges_text = "\n".join(edges)
                    edges_panel = Panel(
                        edges_text,
                        title="[bold magenta]🔗 Stage Transitions[/bold magenta]",
                        border_style="magenta",
                        padding=(0, 2)
                    )
                    self.console.print(edges_panel)

            # Add spacing between stages
            if stage_idx < len(execution_stages) - 1:
                self.console.print()

    def _create_stage_edges(self, from_jobs: list, to_jobs: list, job_deps: dict) -> list:
        """Create edge representations between stages based on execution order"""
        edges = []

        # First, add dependency-based edges
        for from_job in from_jobs:
            dependent_jobs = [to_job for to_job in to_jobs if from_job in job_deps.get(to_job, [])]
            for dep_job in dependent_jobs:
                edges.append(f"[dim cyan]{from_job}[/dim cyan] [bold yellow]⟶[/bold yellow] [dim green]{dep_job}[/dim green]")

        # If no direct dependencies found, show order-based edges
        # This creates a complete execution flow visualization
        if not edges and len(from_jobs) > 0 and len(to_jobs) > 0:
            # For each job in the current stage, connect to all jobs in the next stage
            # This shows the complete execution order flow
            for from_job in from_jobs:
                for to_job in to_jobs:
                    edges.append(f"[dim cyan]{from_job}[/dim cyan] [bold yellow]⟶[/bold yellow] [dim green]{to_job}[/dim green]")

        return edges

    def _draw_execution_order_graph(self, execution_stages: list, job_deps: dict, job_details: dict, workflow) -> None:
        """Draw a graph based on execution paths with stages as groups containing job nodes"""
        if not execution_stages or len(execution_stages) <= 1:
            return

        self.console.print()
        order_title = Text("🔀 Execution Path Graph", style="bold magenta")
        self.console.print(order_title)
        self.console.print()

        # Calculate all execution paths through the workflow
        execution_paths = self._calculate_execution_paths(execution_stages, job_deps)

        if not execution_paths:
            return

        # Display each execution path with stages as groups
        for path_idx, path in enumerate(execution_paths, 1):
            path_title = f"📍 Execution Path {path_idx}"
            path_panel = Panel(
                f"[bold cyan]Path {path_idx}:[/bold cyan] Complete workflow execution sequence",
                title=f"[bold blue]{path_title}[/bold blue]",
                border_style="blue",
                padding=(1, 2)
            )
            self.console.print(path_panel)

            # Group jobs by stages for this path
            path_stages = self._group_path_by_stages(path, execution_stages)

            # Display each stage in the path
            for stage_idx, stage_jobs in enumerate(path_stages):
                self._draw_path_stage_group(stage_idx + 1, stage_jobs, job_details, len(path_stages), workflow)

                # Add connection arrow to next stage (except for last stage)
                if stage_idx < len(path_stages) - 1:
                    self.console.print("      [bold yellow]↓[/bold yellow]")
                    self.console.print()

            # Add spacing between paths
            if path_idx < len(execution_paths):
                self.console.print()

    def _calculate_execution_paths(self, execution_stages: list, job_deps: dict) -> list:
        """Calculate all possible execution paths through the workflow"""
        if not execution_stages:
            return []



        # Start with jobs from the first stage
        current_paths = [[job] for job in execution_stages[0]]

        # For each subsequent stage, extend all current paths
        for stage_idx in range(1, len(execution_stages)):
            next_stage = execution_stages[stage_idx]
            new_paths = []

            for current_path in current_paths:
                last_job = current_path[-1]

                # Find jobs in next stage that can follow this job
                # Either directly dependent or can run after (for parallel stages)
                valid_next_jobs = []
                for next_job in next_stage:
                    # Check if next_job depends on last_job
                    if last_job in job_deps.get(next_job, []):
                        valid_next_jobs.append(next_job)
                    # For parallel stages, allow all jobs if no direct dependency
                    elif stage_idx > 0:
                        # Check if any job in current stage has dependency to next stage
                        has_dependencies = any(
                            any(dep in job_deps.get(next_job, []) for dep in execution_stages[stage_idx - 1])
                            for next_job in next_stage
                        )
                        if not has_dependencies:
                            valid_next_jobs.extend(next_stage)
                            break

                # Remove duplicates
                valid_next_jobs = list(set(valid_next_jobs))

                if valid_next_jobs:
                    for next_job in valid_next_jobs:
                        new_paths.append(current_path + [next_job])
                else:
                    # If no valid next jobs, keep the current path
                    new_paths.append(current_path)

            current_paths = new_paths

        return current_paths

    def _group_path_by_stages(self, path: list, execution_stages: list) -> list:
        """Group jobs in a path by their execution stages"""
        path_stages = []
        for stage in execution_stages:
            # Find jobs in this path that belong to this stage
            stage_jobs_in_path = [job for job in path if job in stage]
            if stage_jobs_in_path:
                path_stages.append(stage_jobs_in_path)
        return path_stages

    def _draw_path_stage_group(self, stage_num: int, stage_jobs: list, job_details: dict, total_stages: int, workflow) -> None:
        """Draw a stage group containing job nodes with step details"""
        # Stage header
        stage_type = ""
        if stage_num == 1:
            stage_type = " [dim](Entry)[/dim]"
        elif stage_num == total_stages:
            stage_type = " [dim](Final)[/dim]"

        stage_header = Panel(
            f"[bold cyan]Stage {stage_num}{stage_type}[/bold cyan]",
            border_style="cyan",
            padding=(0, 1)
        )
        self.console.print(stage_header)

        # Display jobs in this stage
        if len(stage_jobs) == 1:
            job_id = stage_jobs[0]
            job_detail = job_details[job_id]
            self._draw_detailed_job_node(job_id, job_detail, workflow)
        else:
            # Multiple jobs in stage - display in columns
            job_nodes = []
            for job_id in stage_jobs:
                job_detail = job_details[job_id]
                job_node = self._create_detailed_job_panel(job_id, job_detail, workflow)
                job_nodes.append(job_node)

            columns = Columns(job_nodes, equal=True, expand=True)
            self.console.print(columns)

    def _draw_detailed_job_node(self, job_id: str, job_detail: dict, workflow) -> None:
        """Draw a detailed job node with step information"""
        job_panel = self._create_detailed_job_panel(job_id, job_detail, workflow)
        self.console.print(job_panel)

    def _create_detailed_job_panel(self, job_id: str, job_detail: dict, workflow) -> Panel:
        """Create a detailed job panel with step information"""
        # Determine panel style based on job characteristics
        if job_detail['has_outputs'] and job_detail['has_hooks']:
            border_style = "green"
            title_style = "bold green"
            accent_color = "green"
        elif job_detail['has_outputs']:
            border_style = "blue"
            title_style = "bold blue"
            accent_color = "blue"
        elif job_detail['has_hooks']:
            border_style = "yellow"
            title_style = "bold yellow"
            accent_color = "yellow"
        else:
            border_style = "white"
            title_style = "bold white"
            accent_color = "cyan"

        # Create job content with step details
        content_lines = []

        # Job name
        job_name = job_detail['name']
        if len(job_name) > 25:
            job_name = job_name[:22] + "..."
        content_lines.append(f"🎯 [bold {accent_color}]{job_name}[/bold {accent_color}]")

        # Steps info
        steps_text = f"📋 {job_detail['steps']} step{'s' if job_detail['steps'] != 1 else ''}"
        content_lines.append(steps_text)

        # Add feature indicators
        indicators = []
        if job_detail['has_outputs']:
            indicators.append("📤 Outputs")
        if job_detail['has_hooks']:
            indicators.append("🪝 Hooks")

        if indicators:
            content_lines.append(f"[dim italic]{' • '.join(indicators)}[/dim italic]")

        # Add step details from workflow
        if job_id in workflow.jobs:
            job_obj = workflow.jobs[job_id]
            if hasattr(job_obj, 'steps') and job_obj.steps:
                content_lines.append("")  # Empty line before steps
                content_lines.append("[bold]Steps:[/bold]")
                for i, step in enumerate(job_obj.steps, 1):
                    step_name = step.name or f"Step {i}"
                    if len(step_name) > 30:
                        step_name = step_name[:27] + "..."

                    # Determine step type
                    if step.uses:
                        step_type = "🔗 Subworkflow"
                    elif step.run:
                        step_type = "💻 Run"
                    elif step.script:
                        step_type = "🐍 Script"
                    else:
                        step_type = "❓ Unknown"

                    content_lines.append(f"  {i}. [dim]{step_type}[/dim] {step_name}")

        content = "\n".join(content_lines)

        return Panel(
            content,
            title=f"[{title_style}]{job_id}[/{title_style}]",
            border_style=border_style,
            padding=(1, 2),
            title_align="center"
        )

    def _create_stage_edges(self, from_jobs: list, to_jobs: list, job_deps: dict) -> list:
        """Create edge representations between stages based on execution order"""
        edges = []

        # First, add dependency-based edges
        for from_job in from_jobs:
            dependent_jobs = [to_job for to_job in to_jobs if from_job in job_deps.get(to_job, [])]
            for dep_job in dependent_jobs:
                edges.append(f"[dim cyan]{from_job}[/dim cyan] [bold yellow]⟶[/bold yellow] [dim green]{dep_job}[/dim green]")

        # If no direct dependencies found, show order-based edges
        # This creates a complete execution flow visualization
        if not edges and len(from_jobs) > 0 and len(to_jobs) > 0:
            # For each job in the current stage, connect to all jobs in the next stage
            # This shows the complete execution order flow
            for from_job in from_jobs:
                for to_job in to_jobs:
                    edges.append(f"[dim cyan]{from_job}[/dim cyan] [bold yellow]⟶[/bold yellow] [dim green]{to_job}[/dim green]")

        return edges

    def _create_job_panel(self, job_id: str, job_detail: dict) -> Panel:
        """Create a beautiful job panel with Rich styling"""
        # Determine panel style based on job characteristics
        if job_detail['has_outputs'] and job_detail['has_hooks']:
            border_style = "green"
            title_style = "bold green"
            accent_color = "green"
        elif job_detail['has_outputs']:
            border_style = "blue"
            title_style = "bold blue"
            accent_color = "blue"
        elif job_detail['has_hooks']:
            border_style = "yellow"
            title_style = "bold yellow"
            accent_color = "yellow"
        else:
            border_style = "white"
            title_style = "bold white"
            accent_color = "cyan"

        # Create job content
        content = Text()

        # Job name
        job_name = job_detail['name']
        if len(job_name) > 20:
            job_name = job_name[:17] + "..."

        content.append(f"🎯 {job_name}\n", style=f"bold {accent_color}")

        # Steps info
        steps_text = f"📋 {job_detail['steps']} step{'s' if job_detail['steps'] != 1 else ''}"
        content.append(steps_text, style="dim")

        # Add feature indicators
        indicators = []
        if job_detail['has_outputs']:
            indicators.append("📤 Outputs")
        if job_detail['has_hooks']:
            indicators.append("🪝 Hooks")

        if indicators:
            content.append(f"\n{' • '.join(indicators)}", style="dim italic")

        return Panel(
            content,
            title=f"[{title_style}]{job_id}[/{title_style}]",
            border_style=border_style,
            padding=(1, 2),
            title_align="center"
        )

    def _draw_ascii_graph(self, level_jobs: dict, job_deps: dict, job_details: dict) -> list:
        """Draw a clean ASCII graph with proper formatting"""
        lines = []
        max_level = max(level_jobs.keys()) if level_jobs else 0

        if max_level == 0:
            # Simple horizontal layout for jobs with no dependencies
            jobs = level_jobs[0]
            lines.append("Jobs:")
            lines.append("")

            # Create job boxes with standard ASCII
            job_boxes = []
            for job in jobs:
                job_detail = job_details[job]
                job_name = job_detail['name']
                if len(job_name) > 18:
                    job_name = job_name[:15] + "..."

                # Simple box format
                box_width = max(len(job_name) + 4, len(job) + 4, 22)
                box = [
                    f"+{'-' * (box_width - 2)}+",
                    f"| {job_name}{' ' * (box_width - len(job_name) - 2)}|",
                    f"| Steps: {job_detail['steps']}{' ' * (box_width - len(str(job_detail['steps'])) - 8)}|",
                    f"+{'-' * (box_width - 2)}+"
                ]
                job_boxes.append(box)

            # Display boxes horizontally
            for i in range(len(job_boxes[0])):
                line_parts = []
                for box in job_boxes:
                    line_parts.append(box[i])
                lines.append("    ".join(line_parts))

            return lines

        # Multi-level layout with simple vertical flow
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

            # Display jobs in this level
            for job in jobs:
                job_detail = job_details[job]
                job_name = job_detail['name']
                if len(job_name) > 25:
                    job_name = job_name[:22] + "..."

                lines.append(f"  [{job}] {job_name}")
                lines.append(f"    Steps: {job_detail['steps']}")

                # Add feature indicators
                features = []
                if job_detail['has_outputs']:
                    features.append("Outputs")
                if job_detail['has_hooks']:
                    features.append("Hooks")
                if features:
                    lines.append(f"    Features: {', '.join(features)}")

                lines.append("")

            # Add dependency arrows to next level
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
        table = Table(
            title="[bold cyan]📊 Job Specifications[/bold cyan]",
            show_header=True,
            header_style="bold magenta",
            show_lines=True,
            border_style="cyan"
        )

        table.add_column("🎯 Job ID", style="cyan bold", no_wrap=True)
        table.add_column("📝 Name", style="white")
        table.add_column("📋 Steps", justify="center", style="yellow")
        table.add_column("📤 Outputs", justify="center")
        table.add_column("🪝 Hooks", justify="center")

        for job_id, details in job_details.items():
            table.add_row(
                f"[bold]{job_id}[/bold]",
                details['name'],
                str(details['steps']),
                "✅" if details['has_outputs'] else "❌",
                "✅" if details['has_hooks'] else "❌",
            )

        self.console.print(table)

    def _display_job_steps(self, workflow) -> None:
        """Display detailed steps for each job in the workflow with recursive subworkflow support"""
        self.console.print()
        steps_title = Text("📋 Workflow Steps Hierarchy", style="bold magenta")
        self.console.print(steps_title)
        self.console.print()

        # Create a tree structure for the entire workflow
        workflow_tree = Tree(f"🔥 [bold cyan]{workflow.name}[/bold cyan]", guide_style="dim blue")

        for job_id, job in workflow.jobs.items():
            # Job node
            job_node = workflow_tree.add(f"🎯 [bold yellow]{job_id}[/bold yellow] - {job.name or job_id}")
            job_node.add(f"📊 [dim]{len(job.steps)} step{'s' if len(job.steps) != 1 else ''}[/dim]")

            # Add steps with recursive subworkflow support
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

            # Determine step type and content
            if step.uses:
                # This is a subworkflow step
                step_node = parent_node.add(f"{step_prefix}: [bold green]{step_name}[/bold green] (Subworkflow)")
                try:
                    # Load the subworkflow
                    subworkflow = WorkflowRunner.find_flow(step.uses)
                    subworkflow_node = step_node.add(f"🔥 [bold cyan]{subworkflow.name}[/bold cyan] - {subworkflow.description}")

                    # Recursively add subworkflow jobs and steps
                    for sub_job_id, sub_job in subworkflow.jobs.items():
                        sub_job_node = subworkflow_node.add(f"🎯 [bold yellow]{sub_job_id}[/bold yellow] - {sub_job.name or sub_job_id}")
                        sub_job_node.add(f"📊 [dim]{len(sub_job.steps)} step{'s' if len(sub_job.steps) != 1 else ''}[/dim]")
                        self._add_steps_to_tree(sub_job_node, sub_job.steps, depth + 1, max_depth)

                except Exception as e:
                    step_node.add(f"❌ [red]Failed to load subworkflow: {e}[/red]")

            elif step.run:
                # Regular run step
                step_node = parent_node.add(f"{step_prefix}: [bold blue]{step_name}[/bold blue]")
                # Show command (truncated if too long)
                command = step.run.replace('\n', ' ').strip()
                if len(command) > 80:
                    command = command[:77] + "..."
                step_node.add(f"💻 [dim]{command}[/dim]")

            elif step.script:
                # Script step
                step_node = parent_node.add(f"{step_prefix}: [bold purple]{step_name}[/bold purple] (Script)")
                # Show script preview (truncated if too long)
                script = step.script.replace('\n', ' ').strip()
                if len(script) > 80:
                    script = script[:77] + "..."
                step_node.add(f"🐍 [dim]{script}[/dim]")

            else:
                # Unknown step type
                step_node = parent_node.add(f"{step_prefix}: [bold red]{step_name}[/bold red] (Unknown)")
                step_node.add("❓ [dim]No action defined[/dim]")

    def _generate_dot(self, workflow: dict) -> str:
        """Generate DOT format string for the workflow"""
        lines = ["digraph Workflow {", "    rankdir=TB;", "    node [shape=box];"]

        # Add jobs as nodes
        if "jobs" in workflow:
            for job_name, job_config in workflow["jobs"].items():
                # Create node with job name and description
                description = job_config.get("name", job_name) if isinstance(job_config, dict) else str(job_config)
                lines.append(f'    "{job_name}" [label="{job_name}\\n{description}"];')

                # Add dependencies as edges
                if isinstance(job_config, dict) and "needs" in job_config:
                    needs = job_config["needs"]
                    if isinstance(needs, list):
                        for dep in needs:
                            lines.append(f'    "{dep}" -> "{job_name}";')
                    elif isinstance(needs, str):
                        lines.append(f'    "{needs}" -> "{job_name}";')

        lines.append("}")
        return "\n".join(lines)

    def _render_graphviz(self, dot_content: str, output_path: Path, format: str) -> None:
        """Render DOT content using graphviz to specified format"""
        try:
            import subprocess
            import tempfile

            # Create temporary DOT file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.dot', delete=False) as f:
                f.write(dot_content)
                temp_dot = f.name

            # Determine output path with correct extension
            if format.lower() in ['png', 'svg', 'pdf', 'ps', 'jpg', 'jpeg']:
                output_path = output_path.with_suffix(f".{format.lower()}")
            else:
                output_path = output_path.with_suffix(".png")  # default to PNG

            # Run graphviz
            cmd = ["dot", f"-T{format.lower()}", temp_dot, "-o", str(output_path)]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                self.console.print(
                    f"[green]Workflow visualization rendered to:[/green] {output_path}"
                )
            else:
                self.console.print(
                    f"[red]Error rendering graphviz:[/red] {result.stderr}"
                )
                # Fallback to saving DOT file
                dot_output = output_path.with_suffix(".dot")
                dot_output.write_text(dot_content)
                self.console.print(
                    f"[yellow]Saved DOT file instead:[/yellow] {dot_output}"
                )

        except ImportError:
            self.console.print(
                "[yellow]Graphviz not available. Install with: pip install graphviz[/yellow]"
            )
            # Fallback to saving DOT file
            dot_output = output_path.with_suffix(".dot")
            dot_output.write_text(dot_content)
            self.console.print(f"[green]Saved DOT file to:[/green] {dot_output}")
        except Exception as e:
            self.console.print(f"[red]Error rendering visualization:[/red] {e}")
            # Fallback to saving DOT file
            dot_output = output_path.with_suffix(".dot")
            dot_output.write_text(dot_content)
            self.console.print(f"[green]Saved DOT file to:[/green] {dot_output}")

    def _calculate_dependency_levels(self, root_jobs: list, job_deps: dict) -> dict:
        """Calculate the dependency level for each job"""
        levels = {}

        # Start with root jobs at level 0
        for job in root_jobs:
            levels[job] = 0

        # Iteratively calculate levels
        changed = True
        while changed:
            changed = False
            for job, deps in job_deps.items():
                if job not in levels:
                    # Job hasn't been assigned a level yet
                    if all(dep in levels for dep in deps):
                        # All dependencies are satisfied, assign level
                        max_dep_level = max(levels[dep] for dep in deps) if deps else -1
                        levels[job] = max_dep_level + 1
                        changed = True
                else:
                    # Job already has a level, check if it needs to be updated
                    if deps:
                        max_dep_level = max(levels[dep] for dep in deps)
                        required_level = max_dep_level + 1
                        if required_level > levels[job]:
                            levels[job] = required_level
                            changed = True

        return levels
