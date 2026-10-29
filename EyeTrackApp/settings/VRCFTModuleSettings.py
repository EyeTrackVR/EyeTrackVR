from queue import Empty, Full, Queue

from config import EyeTrackConfig
from eye import EyeId
from osc.OSCMessage import OSCMessage, OSCMessageType
from settings.BaseSettings import BaseSettingsWidget
from settings.modules.VRCFTSettingsModule import VRCFTSettingsModule


class VRCFTSettingsWidget(BaseSettingsWidget):
    def __init__(
        self,
        widget_id: EyeId,
        main_config: EyeTrackConfig,
        osc_queue_in: Queue[OSCMessage],
    ):
        self.osc_queue = osc_queue_in
        settings_modules = [
            VRCFTSettingsModule,
        ]

        super().__init__(widget_id, main_config, settings_modules)

    def _enqueue_osc_message(self, osc_message: OSCMessage) -> None:
        try:
            self.osc_queue.put_nowait(osc_message)
            return
        except Full:
            pass

        try:
            self.osc_queue.get_nowait()
        except Empty:
            pass

        try:
            self.osc_queue.put_nowait(osc_message)
        except Full:
            pass

    def _update_and_save_config(self, validated_data: dict):
        self.main_config.update(validated_data, save=True)

        for field, value in validated_data.items():
            self._enqueue_osc_message(
                OSCMessage(
                    type=OSCMessageType.VRCFT_MODULE_INFO,
                    data={
                        "command": "set",
                        "field": field,
                        "value": value,
                    },
                )
            )

        self.is_saving = False
