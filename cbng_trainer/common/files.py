from typing import Optional
from urllib.parse import quote


def calculate_target_path(
    base_url: str,
    target_group: str,
    target_instance: str,
    target_type: str,
    target_file: Optional[str] = None,
    create_plots: bool = False,
) -> str:
    endpoint = f'{base_url.lstrip("/")}'
    if create_plots:
        endpoint += f"/api/create-plots"

    endpoint += f"/{quote(target_group)}/{quote(target_instance)}/{quote(target_type)}"
    if target_file:
        endpoint += f"/{quote(target_file)}"
    return endpoint
