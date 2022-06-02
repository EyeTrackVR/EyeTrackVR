
import kivy
from multiprocessing import Process,Queue,Pipe  
kivy.require("1.9.1")
from kivy.app import App
from kivy.uix.gridlayout import GridLayout
from kivy.uix.slider import Slider
from kivy.uix.label import Label
from kivy.uix.floatlayout import FloatLayout 
from kivy.properties  import NumericProperty
from kivy.uix.scatter import Scatter
from kivy.uix.textinput import TextInput
from kivy.uix.boxlayout import BoxLayout
from kivy.core.window import Window
import time
import cv2



###############################################################################

Window.size = (600, 60)

class WidgetContainer(GridLayout):
 
    def __init__(self, **kwargs):

        super(WidgetContainer, self).__init__(**kwargs)




############################################################################### right

        self.cols = 3
        self.xcc = Slider(min = 20, max = 200,
        value_track = True,
        value_track_color =[1, 1, 1, 1])
        self.add_widget(Label(text ='Threshold'))
        self.add_widget(self.xcc)        
        self.xValue = Label(text ='Select')        
        self.add_widget(self.xValue)
        self.xcc.bind(value = self.on_value)
        



        self.rota = Slider(min = 0, max = 360,
        value_track = True,
        value_track_color =[1, 1, 1, 1])
        self.add_widget(Label(text ='Rotation'))
        self.add_widget(self.rota)
        self.rotav= Label(text ='Select')
        self.add_widget(self.rotav)
        self.rota.bind(value = self.on_value1)



    def on_value(self, instance, brightness):
        self.xValue.text = "% d"% brightness
        confg.fx = self.xValue.text
        configsave()
        time.sleep(0.1)


    def on_value1(self, instance, brightness):
        self.rotav.text = "% d"% brightness
        confg.rv = self.rotav.text
        configsave()
        time.sleep(0.1)



class EyetrackGUI(App):
    def build(self):
        widgetContainer = WidgetContainer()
        print()
        
        return widgetContainer
 


def confg():

    confg.fx = 128
    confg.rv = 0



def configsave():
    with open('settings.cfg', 'w+') as rf:
        rf.write(str(confg.fx))
        rf.write('\n')
        rf.write(str(confg.rv))
            


confg()

rootGUI = EyetrackGUI()
   

rootGUI.run()
