from osc.OSCMessage import OSCMessage


class VRCFTModule:
    def send(self):
        pass

    def receive(self):
        pass

    # def handle_osc_message(self, osc_message: OSCMessage, client):
    #     message = self.create_osc_message(
    #         "set", osc_message.data.field, osc_message.data.value
    #     )

    def serialize_osc_message(self, action, field=None, value=None):
        pass

    def deserialize_osc_message(self, message):
        pass
