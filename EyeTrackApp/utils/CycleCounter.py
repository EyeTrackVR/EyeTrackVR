#Counts how many cycles a condition has been true
class CycleCounter:
    def __init__ (self, max_count):
        self.count = 0
        self.max_count = max_count

    def increase(self):
        self.count += 1
        self.count = min(self.count,self.max_count)
    
    def decrease(self):
        self.count -= 1
        self.count = max(self.count,0)

    def reset(self):
        self.count = 0

    def is_complete(self):
        if self.count >= self.max_count:
            return True
        return False
    
    def active(self):
        if self.count == 0:
            return False
        else:
            return True
        
    def get_count(self):
        return self.count
    
    def update(self,max_count):
        self.max_count = max_count

    def force_complete(self):
        self.count = self.max_count

    def less_than_percentage(self,mult):
        return self.count <= self.max_count * mult