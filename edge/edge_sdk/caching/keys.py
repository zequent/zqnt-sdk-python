from enum import Enum


class CacheKeys(Enum):
    ASSET_ONLINE = "zqnt:asset-online:"
    ASSET_MODE = "zqnt:asset-mode:"
    TELEMETRY = "zqnt:telemetry:{sn}"
    ASSET_LINK_TELEMETRY = "zqnt:asset-link-telemetry:"
    ASSET_EXTENDED_TELEMTRY = "zqnt:asset-extended-telemetry:"
    ASSET_MANUAL_CONTROL_STATE = "zqnt:drc-state:"
    ASSET_LIVE_STREAM_STATE = "zqnt:live-stream-state:"
    ASSET_SERVICES_REPLY_WAIT = "zqnt:asset-task-reply-wait:{tid}:{method}"
    ASSET_ACTIVE_TASKS = "zqnt:asset-active-tasks:{sn}:{taskId}"
    ASSET_COMPLETED_TASKS = "zqnt:asset-completed-tasks:{sn}:{taskId}"
    ASSET_TASK_EXTERNAL_ID_REFERENCE = "zqnt:asset-task-external-id-reference:{externalId}:{sn}"
    ASSET_MANUAL_CONTROL_REQUEST = "zqnt:asset-manual-control-request:"
    SUBASSET_AT_HOME = "zqnt:subaset-at-home:"
    ASSET_SUBASSET_REFERENCE = "zqnt:asset-subasset-reference:"
    ASSET_PROPERTIES = "zqnt:asset-properties:"
    ASSET_DTO = "zqnt:asset-dto:{sn}"
    SUBASSET_DTO = "zqnt:subasset-dto:{subAssetSn}"
    EDGE_ENDPOINTS = "zqnt:edge-endpoints:{vendor}"
    EDGE_VENDOR = "zqnt:edge-vendor:{sn}"
    ASSET_CURRENT_TASK = "zqnt:asset-current-task:{sn}"

    def build(self, **kwargs: str) -> str:
        return self.value.format(**kwargs)
