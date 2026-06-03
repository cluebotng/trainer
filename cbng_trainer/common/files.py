from typing import Optional
from urllib.parse import quote


def calculate_target_path(
    base_url: str,
    target_group: str,
    target_instance: str,
    target_type: str,
    target_file: Optional[str] = None,
) -> str:
    endpoint = f'{base_url.rstrip("/")}'
    endpoint += f"/{quote(target_group)}/{quote(target_instance)}/{quote(target_type)}"
    if target_file:
        endpoint += f"/{quote(target_file)}"
    return endpoint
