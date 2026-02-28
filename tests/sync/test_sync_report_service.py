from SYNC_APP.APP.SERVICES.report_service import ReportService
from SYNC_APP.APP.types import StatusReport


def test_get_formatted_status():
    svc = ReportService()
    assert svc.get_formatted_status(StatusReport.INFO) == "[green]INFO[/green]"
    assert (
            svc.get_formatted_status(StatusReport.IMPORTANT_INFO)
            == "[bold green]IMPORTANT_INFO[/bold green]"
    )
    assert (
            svc.get_formatted_status(StatusReport.WARNING)
            == "[bright_yellow]WARNING[/bright_yellow]"
    )
    assert svc.get_formatted_status(StatusReport.ERROR) == "[red]ERROR[/red]"
    assert svc.get_formatted_status(StatusReport.FATAL) == "[bold red]FATAL[/bold red]"
