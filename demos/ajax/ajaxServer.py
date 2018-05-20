from tornado.ioloop import IOLoop
from tornado.web import RequestHandler, Application
from tornado.httpserver import HTTPServer
import os
import json
class QuestionHandler(RequestHandler):
    
    def set_default_headers(self):
        print "setting headers!!!"
        self.set_header("Access-Control-Allow-Origin", "*")
        #self.set_header("Access-Control-Allow-Headers", "x-requested-with")
        self.set_header('Access-Control-Allow-Methods', 'GET, OPTIONS')
    
    
    def get(self):
        #extract response
        question=self.get_argument('question')         
       
        #Return the response 
        response='recieved '+ question
        jsonData = {
        'status' : 200,
        'message' : "OK",
        'answer' : response
        }
        jsonData=json.dumps(jsonData)
        self.write(jsonData)
    def write_error(self,status_code,**kwargs):
        jsonData = {
        'status' : int(status_code),
        'message' : "Internal server error",
        'answer' : 'NULL'
        }
        self.write(jsonData)
    def options(self):
        self.set_status(204)
        self.finish()
    

application=Application([(
		r"/faq",
		QuestionHandler
	)])

if __name__ == "__main__":
	server = HTTPServer(application)
	server.listen(os.environ.get("PORT", 8888))
	IOLoop.current().start()
