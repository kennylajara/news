"""
CLI commands for LLM API call logs.
"""

import click
from datetime import datetime, timedelta
from tabulate import tabulate
from db import Database
from db.models import LLMApiCall
from sqlalchemy import func, desc


@click.group()
def llm():
    """Manage and analyze LLM API call logs."""
    pass


@llm.command()
@click.option('--days', default=7, help='Number of days to include in stats (default: 7)')
def stats(days):
    """Show statistics of LLM API usage."""
    db = Database()
    session = db.get_session()

    try:
        # Calculate date range
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        # Total calls
        total_calls = session.query(LLMApiCall).filter(
            LLMApiCall.started_at >= cutoff_date
        ).count()

        # Success rate
        successful_calls = session.query(LLMApiCall).filter(
            LLMApiCall.started_at >= cutoff_date,
            LLMApiCall.success == 1
        ).count()
        success_rate = (successful_calls / total_calls * 100) if total_calls > 0 else 0

        # Token usage
        token_stats = session.query(
            func.sum(LLMApiCall.input_tokens).label('total_input'),
            func.sum(LLMApiCall.output_tokens).label('total_output'),
            func.sum(LLMApiCall.total_tokens).label('total')
        ).filter(
            LLMApiCall.started_at >= cutoff_date
        ).first()

        total_input = token_stats.total_input or 0
        total_output = token_stats.total_output or 0
        total_tokens = token_stats.total or 0

        # Average duration
        avg_duration = session.query(
            func.avg(LLMApiCall.duration_ms)
        ).filter(
            LLMApiCall.started_at >= cutoff_date,
            LLMApiCall.duration_ms.isnot(None)
        ).scalar()

        avg_duration_ms = int(avg_duration) if avg_duration else 0

        # Calls by task
        calls_by_task = session.query(
            LLMApiCall.task_name,
            func.count(LLMApiCall.id).label('count')
        ).filter(
            LLMApiCall.started_at >= cutoff_date
        ).group_by(LLMApiCall.task_name).order_by(desc('count')).all()

        # Calls by model
        calls_by_model = session.query(
            LLMApiCall.model,
            func.count(LLMApiCall.id).label('count')
        ).filter(
            LLMApiCall.started_at >= cutoff_date
        ).group_by(LLMApiCall.model).order_by(desc('count')).all()

        # Print stats
        click.echo(click.style(f"\nLLM API Usage Statistics (Last {days} days)", fg='cyan', bold=True))
        click.echo(click.style("=" * 50, fg='cyan'))
        click.echo()

        # Overview
        click.echo(click.style("Overview:", fg='yellow', bold=True))
        overview_table = [
            ['Total Calls', click.style(str(total_calls), fg='green')],
            ['Successful', click.style(str(successful_calls), fg='green')],
            ['Failed', click.style(str(total_calls - successful_calls), fg='red')],
            ['Success Rate', click.style(f"{success_rate:.1f}%", fg='green')],
            ['Avg Duration', click.style(f"{avg_duration_ms}ms", fg='blue')]
        ]
        click.echo(tabulate(overview_table, tablefmt='plain'))
        click.echo()

        # Token usage
        click.echo(click.style("Token Usage:", fg='yellow', bold=True))
        token_table = [
            ['Input Tokens', click.style(f"{total_input:,}", fg='cyan')],
            ['Output Tokens', click.style(f"{total_output:,}", fg='cyan')],
            ['Total Tokens', click.style(f"{total_tokens:,}", fg='green', bold=True)]
        ]
        click.echo(tabulate(token_table, tablefmt='plain'))
        click.echo()

        # Calls by task
        if calls_by_task:
            click.echo(click.style("Calls by Task:", fg='yellow', bold=True))
            task_table = [[task or '(none)', count] for task, count in calls_by_task]
            click.echo(tabulate(task_table, headers=['Task', 'Calls'], tablefmt='simple'))
            click.echo()

        # Calls by model
        if calls_by_model:
            click.echo(click.style("Calls by Model:", fg='yellow', bold=True))
            model_table = [[model, count] for model, count in calls_by_model]
            click.echo(tabulate(model_table, headers=['Model', 'Calls'], tablefmt='simple'))
            click.echo()

    finally:
        session.close()


@llm.command()
@click.option('--limit', default=20, help='Number of recent calls to show (default: 20)')
@click.option('--task', help='Filter by task name')
@click.option('--model', help='Filter by model')
@click.option('--success/--errors', default=None, help='Filter by success/error status')
def list(limit, task, model, success):
    """List recent LLM API calls."""
    db = Database()
    session = db.get_session()

    try:
        # Build query
        query = session.query(LLMApiCall).order_by(desc(LLMApiCall.started_at))

        if task:
            query = query.filter(LLMApiCall.task_name == task)
        if model:
            query = query.filter(LLMApiCall.model == model)
        if success is not None:
            query = query.filter(LLMApiCall.success == (1 if success else 0))

        calls = query.limit(limit).all()

        if not calls:
            click.echo(click.style("No API calls found.", fg='yellow'))
            return

        # Format table
        table_data = []
        for call in calls:
            status = click.style('✓', fg='green') if call.success else click.style('✗', fg='red')
            duration = f"{call.duration_ms}ms" if call.duration_ms else 'N/A'
            tokens = f"{call.total_tokens}" if call.total_tokens else 'N/A'
            started = call.started_at.strftime('%Y-%m-%d %H:%M:%S')

            table_data.append([
                call.id,
                status,
                call.task_name or '(none)',
                call.model,
                tokens,
                duration,
                started
            ])

        click.echo()
        click.echo(tabulate(
            table_data,
            headers=['ID', '✓', 'Task', 'Model', 'Tokens', 'Duration', 'Started'],
            tablefmt='simple'
        ))
        click.echo()
        click.echo(click.style(f"Showing {len(calls)} most recent call(s)", fg='cyan'))
        click.echo()

    finally:
        session.close()


@llm.command()
@click.argument('call_id', type=int)
@click.option('--show-prompts/--no-prompts', default=False, help='Show full prompts')
@click.option('--show-response/--no-response', default=False, help='Show full response')
@click.option('--show-output/--no-output', default=False, help='Show parsed output')
def show(call_id, show_prompts, show_response, show_output):
    """Show detailed information about a specific API call."""
    db = Database()
    session = db.get_session()

    try:
        call = session.query(LLMApiCall).filter(LLMApiCall.id == call_id).first()

        if not call:
            click.echo(click.style(f"API call #{call_id} not found.", fg='red'))
            return

        # Header
        status = click.style('SUCCESS', fg='green') if call.success else click.style('ERROR', fg='red')
        click.echo()
        click.echo(click.style(f"LLM API Call #{call.id} - {status}", fg='cyan', bold=True))
        click.echo(click.style("=" * 60, fg='cyan'))
        click.echo()

        # Basic info
        click.echo(click.style("Basic Info:", fg='yellow', bold=True))
        info_table = [
            ['Call Type', call.call_type],
            ['Task Name', call.task_name or '(none)'],
            ['Model', call.model],
            ['Started', call.started_at.strftime('%Y-%m-%d %H:%M:%S UTC')],
            ['Completed', call.completed_at.strftime('%Y-%m-%d %H:%M:%S UTC') if call.completed_at else 'N/A'],
            ['Duration', f"{call.duration_ms}ms" if call.duration_ms else 'N/A']
        ]
        click.echo(tabulate(info_table, tablefmt='plain'))
        click.echo()

        # Token usage
        click.echo(click.style("Token Usage:", fg='yellow', bold=True))
        token_table = [
            ['Input Tokens', call.input_tokens or 'N/A'],
            ['Output Tokens', call.output_tokens or 'N/A'],
            ['Total Tokens', call.total_tokens or 'N/A']
        ]
        click.echo(tabulate(token_table, tablefmt='plain'))
        click.echo()

        # Context data
        if call.context_data:
            click.echo(click.style("Context Data:", fg='yellow', bold=True))
            import json
            click.echo(json.dumps(call.context_data, indent=2))
            click.echo()

        # Error message
        if call.error_message:
            click.echo(click.style("Error Message:", fg='red', bold=True))
            click.echo(call.error_message)
            click.echo()

        # Prompts
        if show_prompts:
            if call.system_prompt:
                click.echo(click.style("System Prompt:", fg='yellow', bold=True))
                click.echo(call.system_prompt)
                click.echo()

            if call.user_prompt:
                click.echo(click.style("User Prompt:", fg='yellow', bold=True))
                click.echo(call.user_prompt)
                click.echo()

            if call.messages:
                click.echo(click.style("Messages:", fg='yellow', bold=True))
                import json
                click.echo(json.dumps(call.messages, indent=2))
                click.echo()

        # Response
        if show_response and call.response_raw:
            click.echo(click.style("Raw Response:", fg='yellow', bold=True))
            import json
            click.echo(json.dumps(call.response_raw, indent=2))
            click.echo()

        # Parsed output
        if show_output and call.parsed_output:
            click.echo(click.style("Parsed Output:", fg='yellow', bold=True))
            import json
            click.echo(json.dumps(call.parsed_output, indent=2))
            click.echo()

    finally:
        session.close()


@llm.command()
@click.option('--by', type=click.Choice(['task', 'model', 'hour', 'day']), default='task', help='Group by (default: task)')
@click.option('--days', default=7, help='Number of days to analyze (default: 7)')
def analyze(by, days):
    """Analyze LLM API usage patterns."""
    db = Database()
    session = db.get_session()

    try:
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        if by == 'task':
            # Analyze by task
            results = session.query(
                LLMApiCall.task_name,
                func.count(LLMApiCall.id).label('calls'),
                func.sum(LLMApiCall.total_tokens).label('tokens'),
                func.avg(LLMApiCall.duration_ms).label('avg_duration'),
                func.sum(LLMApiCall.success).label('successes')
            ).filter(
                LLMApiCall.started_at >= cutoff_date
            ).group_by(LLMApiCall.task_name).order_by(desc('calls')).all()

            click.echo()
            click.echo(click.style(f"Analysis by Task (Last {days} days)", fg='cyan', bold=True))
            click.echo(click.style("=" * 80, fg='cyan'))
            click.echo()

            table_data = []
            for task, calls, tokens, avg_dur, successes in results:
                success_rate = (successes / calls * 100) if calls > 0 else 0
                table_data.append([
                    task or '(none)',
                    calls,
                    f"{tokens or 0:,}",
                    f"{int(avg_dur) if avg_dur else 0}ms",
                    f"{success_rate:.1f}%"
                ])

            click.echo(tabulate(
                table_data,
                headers=['Task', 'Calls', 'Tokens', 'Avg Duration', 'Success Rate'],
                tablefmt='simple'
            ))
            click.echo()

        elif by == 'model':
            # Analyze by model
            results = session.query(
                LLMApiCall.model,
                func.count(LLMApiCall.id).label('calls'),
                func.sum(LLMApiCall.total_tokens).label('tokens'),
                func.avg(LLMApiCall.duration_ms).label('avg_duration'),
                func.sum(LLMApiCall.success).label('successes')
            ).filter(
                LLMApiCall.started_at >= cutoff_date
            ).group_by(LLMApiCall.model).order_by(desc('calls')).all()

            click.echo()
            click.echo(click.style(f"Analysis by Model (Last {days} days)", fg='cyan', bold=True))
            click.echo(click.style("=" * 80, fg='cyan'))
            click.echo()

            table_data = []
            for model, calls, tokens, avg_dur, successes in results:
                success_rate = (successes / calls * 100) if calls > 0 else 0
                table_data.append([
                    model,
                    calls,
                    f"{tokens or 0:,}",
                    f"{int(avg_dur) if avg_dur else 0}ms",
                    f"{success_rate:.1f}%"
                ])

            click.echo(tabulate(
                table_data,
                headers=['Model', 'Calls', 'Tokens', 'Avg Duration', 'Success Rate'],
                tablefmt='simple'
            ))
            click.echo()

        elif by in ['hour', 'day']:
            # Analyze by time period
            from sqlalchemy import extract

            if by == 'hour':
                time_field = func.strftime('%Y-%m-%d %H:00', LLMApiCall.started_at)
                label = 'Hour'
            else:
                time_field = func.strftime('%Y-%m-%d', LLMApiCall.started_at)
                label = 'Day'

            results = session.query(
                time_field.label('period'),
                func.count(LLMApiCall.id).label('calls'),
                func.sum(LLMApiCall.total_tokens).label('tokens')
            ).filter(
                LLMApiCall.started_at >= cutoff_date
            ).group_by('period').order_by('period').all()

            click.echo()
            click.echo(click.style(f"Analysis by {label} (Last {days} days)", fg='cyan', bold=True))
            click.echo(click.style("=" * 60, fg='cyan'))
            click.echo()

            table_data = [[period, calls, f"{tokens or 0:,}"] for period, calls, tokens in results]
            click.echo(tabulate(
                table_data,
                headers=[label, 'Calls', 'Tokens'],
                tablefmt='simple'
            ))
            click.echo()

    finally:
        session.close()
