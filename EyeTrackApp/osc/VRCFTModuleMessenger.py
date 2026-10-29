from pythonosc.udp_client import SimpleUDPClient
from osc.OSCMessage import OSCMessage


class VRCFTModuleSender:
    set_command_pattern = "/command/{}/{}/"

    def send(self, osc_message: OSCMessage, client: SimpleUDPClient):
        command = osc_message.data.get("command", None)
        field_to_send = osc_message.data.get("field", None)
        value_to_send = osc_message.data.get("value", None)

        if not command or not all([field_to_send, value_to_send is not None]):
            print("[ERROR] Misconfiguration in received OSC message for the VRCFT Module")
            return

        client.send_message(self.set_command_pattern.format(command, field_to_send), value_to_send)
