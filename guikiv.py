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
Window.size = (500, 200)

class WidgetContainer(GridLayout):
 
    def __init__(self, **kwargs):


        super(WidgetContainer, self).__init__(**kwargs)
 
      
        self.cols = 3
         

        self.xcc = Slider(min = 1, max = 800,
        value_track = True,
        value_track_color =[1, 1, 1, 1])
          
  
        self.add_widget(Label(text ='Search Size X R'))
        self.add_widget(self.xcc)
 

        
        self.xValue = Label(text ='1')
        
        self.add_widget(self.xValue)
     

        self.xcc.bind(value = self.on_value)
        
        ###################################


        self.Y = Slider(min = 1, max = 2000,
        value_track = True,
        value_track_color =[1, 1, 1, 1])
          
  
        self.add_widget(Label(text ='Search Size Y R'))
        self.add_widget(self.Y)
 

        
        self.YV = Label(text ='1')
        self.add_widget(self.YV)
        
 

        self.Y.bind(value = self.on_value1)
        ###############################################

        self.xlc = Slider(min = 1, max = 800,
        value_track = True,
        value_track_color =[1, 1, 1, 1])   
        self.add_widget(Label(text ='Search Size X L'))
        self.add_widget(self.xlc)
        self.xlValue = Label(text ='1')
        self.add_widget(self.xlValue)
        self.xlc.bind(value = self.on_value2)
        ####################################################

        self.ylc = Slider(min = 1, max = 800,
        value_track = True,
        value_track_color =[1, 1, 1, 1])
        self.add_widget(Label(text ='Search Size Y L'))
        self.add_widget(self.ylc)
        self.ylValue = Label(text ='1')
        self.add_widget(self.ylValue)
        self.ylc.bind(value = self.on_value3)
        
#####################################################

    def on_value(self, instance, brightness):
        self.xValue.text = "% d"% brightness
        fx= open("valueX.txt","w+")
        fx.write(self.xValue.text)
        fx.close

    def on_value1(self, instance, brightness,):
        self.YV.text = "% d"% brightness
        fy= open("valueY.txt","w+")
        fy.write(self.YV.text)
        fy.close

    def on_value2(self, instance, brightness):
        self.xlValue.text = "% d"% brightness
        fxl= open("valueXl.txt","w+")
        fxl.write(self.xlValue.text)
        fxl.close

    def on_value3(self, instance, brightness,):
        self.ylValue.text = "% d"% brightness
        fyl= open("valueYl.txt","w+")
        fyl.write(self.ylValue.text)
        fyl.close


class Eyetrack(App):
    def build(self):
        widgetContainer = WidgetContainer()
        print()
        
        return widgetContainer
 

root = Eyetrack()
   

root.run()