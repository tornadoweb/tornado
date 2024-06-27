<!-----

You have some errors, warnings, or alerts. If you are using reckless mode, turn it off to see inline alerts.
* ERRORs: 0
* WARNINGs: 0
* ALERTS: 27

Conversion time: 7.951 seconds.


Using this Markdown file:

1. Paste this output into your source file.
2. See the notes and action items below regarding this conversion run.
3. Check the rendered output (headings, lists, code blocks, tables) for proper
   formatting and use a linkchecker before you publish this page.

Conversion notes:

* Docs to Markdown version 1.0β36
* Thu Jun 27 2024 12:09:33 GMT-0700 (PDT)
* Source doc: README.md
* This document has images: check for >>>>>  gd2md-html alert:  inline image link in generated source and store images to your server. NOTE: Images in exported zip file from Google Docs may not appear in  the same order as they do in your doc. Please check the images!

----->


<p style="color: red; font-weight: bold">>>>>>  gd2md-html alert:  ERRORs: 0; WARNINGs: 0; ALERTS: 27.</p>
<ul style="color: red; font-weight: bold"><li>See top comment block for details on ERRORs and WARNINGs. <li>In the converted Markdown or HTML, search for inline alerts that start with >>>>>  gd2md-html alert:  for specific instances that need correction.</ul>

<p style="color: red; font-weight: bold">Links to alert messages:</p><a href="#gdcalert1">alert1</a>
<a href="#gdcalert2">alert2</a>
<a href="#gdcalert3">alert3</a>
<a href="#gdcalert4">alert4</a>
<a href="#gdcalert5">alert5</a>
<a href="#gdcalert6">alert6</a>
<a href="#gdcalert7">alert7</a>
<a href="#gdcalert8">alert8</a>
<a href="#gdcalert9">alert9</a>
<a href="#gdcalert10">alert10</a>
<a href="#gdcalert11">alert11</a>
<a href="#gdcalert12">alert12</a>
<a href="#gdcalert13">alert13</a>
<a href="#gdcalert14">alert14</a>
<a href="#gdcalert15">alert15</a>
<a href="#gdcalert16">alert16</a>
<a href="#gdcalert17">alert17</a>
<a href="#gdcalert18">alert18</a>
<a href="#gdcalert19">alert19</a>
<a href="#gdcalert20">alert20</a>
<a href="#gdcalert21">alert21</a>
<a href="#gdcalert22">alert22</a>
<a href="#gdcalert23">alert23</a>
<a href="#gdcalert24">alert24</a>
<a href="#gdcalert25">alert25</a>
<a href="#gdcalert26">alert26</a>
<a href="#gdcalert27">alert27</a>

<p style="color: red; font-weight: bold">>>>>> PLEASE check and correct alert issues and delete this message and the inline alerts.<hr></p>


**SEP Assignment 1**

**Team 72**

**<span style="text-decoration:underline;">Project Chosen</span>**

**Name:** Tornado

**URL:** [https://github.com/tornadoweb/tornado](https://github.com/tornadoweb/tornado)

**Number of Lines:** 36,634

**Tool used to count number of lines:** Lizard

**Programming Language: **Python

**<span style="text-decoration:underline;">Coverage Measurement</span>**

**Existing tool**

The tool used to find the existing coverage of our chosen repository was coverage.py. To find the coverage of each file within the repository, we followed a few steps: 



1. Go to the repository's root directory.
2. Run this command in the terminal:** coverage run -m tornado.test.runtests (.coveragerc)**
3. Wait for the tests to finish and then run the next command: **coverage report. **This shows a quick overview of the coverage of the repository.
4. Run **coverage html.** Open the htmlcov folder and view index.html on the browser. This shows the coverage of each file and once a file is clicked, shows which lines are covered by the tests. 

    **<span style="text-decoration:underline;">Note: </span>**

    * When testing for changes and re-running the coverage, run **coverage erase** to reset the coverage then follow steps 1 to 4.
    * Make sure to properly install all dependencies such as pycurl, running **pip install -r requirements.txt **does not work all the time. You can do this by running: pip install pycurl==7.45.3 for the specific version (required for cul_hhtpclient).

**Coverage Results**



<p id="gdcalert1" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image1.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert2">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image1.png "image_tooltip")


**<span style="text-decoration:underline;">**Note:</span>** We output the instrumentation results to corresponding text files as functions are called many times during testing and clutter up the terminal. For example, the instrumentation results of the ‘_reload’ function in the ‘autoreload.py’ file will be stored in ‘autoreload_reload.txt’. To print the branches, we print the whole dictionary in the text file when the function is called.

**Your Own Coverage Tool**

**Tanishq Gupta**

**1.__check__file** in autoreload.py

&lt;Show a patch (diff) or a link to a commit made in your forked repository that shows the instrumented code to gather coverage measurements>

&lt;Provide a screenshot of the coverage results output by the instrumentation>

**2. main** in autoreload.py

&lt;Provide the same kind of information provided for Function 1>



**Devansh**



1. **def _stderr_supports_color() **in log.py

Coverage results of our own coverage tool:



2. **def start()**  in autoreload.py

	

<p id="gdcalert2" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image2.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert3">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image2.png "image_tooltip")


Coverage results of our own coverage tool:



<p id="gdcalert3" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image3.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert4">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image3.png "image_tooltip")


**Pedro Escobin**



1. **def _curl_create(self)** in curl_httpclient.py

Patch (diff) of the commit that shows the instrumented code: 



<p id="gdcalert4" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image4.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert5">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image4.png "image_tooltip")


Coverage results of our own coverage tool: 


            

<p id="gdcalert5" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image5.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert6">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image5.png "image_tooltip")



        	



2. **def _curl_debug(self, debug_type: int, debug_msg: str) -> None **in curl_httpclient.py

Patch (diff) of the commit that shows the instrumented code: 



<p id="gdcalert6" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image6.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert7">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image6.png "image_tooltip")




Coverage results of our own coverage tool: 


        

<p id="gdcalert7" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image7.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert8">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image7.png "image_tooltip")


**Shubhra Mohan Singh**



1. **_reload**  in autoreload.py

&lt;Show a patch (diff) or a link to a commit made in your forked repository that shows the instrumented code to gather coverage measurements>



<p id="gdcalert8" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image8.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert9">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image8.png "image_tooltip")




<p id="gdcalert9" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image9.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert10">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image9.png "image_tooltip")


&lt;Provide a screenshot of the coverage results output by the instrumentation>



<p id="gdcalert10" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image10.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert11">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image10.png "image_tooltip")






2. **_reload_on_update ** in autoreload.py

	



<p id="gdcalert11" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image11.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert12">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image11.png "image_tooltip")



    

<p id="gdcalert12" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image12.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert13">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image12.png "image_tooltip")


&lt;Provide the same kind of information provided for Function 1>



<p id="gdcalert13" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image13.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert14">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image13.png "image_tooltip")


		



**<span style="text-decoration:underline;">Coverage improvement</span>**

**Individual tests**

**Tanishq Gupta**

**Tests to cover the _check_file function,**


```
def test_file_stat_exception(self, mock_stat):
def test_file_not_in_modify_times(self, mock_stat):
def test_file_in_modify_times_no_change(self, mock_stat):
def test_file_in_modify_times_with_change(self, mock_reload, mock_log, mock_stat):
```


&lt;Show a patch (diff) or a link to a commit made in your forked repository that shows the new/enhanced test>

&lt;Provide a screenshot of the old coverage results (the same as you already showed above)>

&lt;Provide a screenshot of the new coverage results>

&lt;State the coverage improvement with a number and elaborate on why the coverage is improved>

The _check_file function was initially 0% covered and then it improved to 100%. This is because of the 4 functions I created which ensure that the _check_file function handles various scenarios correctly, such as exceptions during file checks, new files, unchanged files, and modified files, ensuring the appropriate actions are taken in each case.

<span style="text-decoration:underline;">Test 1: test_file_stat_exception</span> -> This test checks the behavior when an exception occurs while trying to get the file status.

<span style="text-decoration:underline;">Test 2: test_file_not_in_modify_times</span> -> This test verifies the behavior when a new file is checked for the first time.

<span style="text-decoration:underline;">Test 3: test_file_in_modify_times_no_change</span> -> This test verifies the behavior when a file’s modification time has not changed since the last check.

<span style="text-decoration:underline;">Test 4: test_file_in_modify_times_with_change</span> -> This test verifies the behavior when a file’s modification time has changed since the last check, and the server needs to be restarted.

**Tests to cover the main function,**


```
def test_main_with_module(self, mock_spec, mock_argv, mock_is_main, mock_watch, mock_wait):
   def test_main_with_path(self, mock_spec, mock_argv, mock_is_main, mock_watch, mock_wait):
   def test_main_syntax_error(self, mock_spec, mock_argv, mock_is_main, mock_watch, mock_wait):
   def test_main_uncaught_exception(self, mock_spec, mock_argv, mock_is_main, mock_watch, mock_wait):
   def test_main_exit_success(self, mock_spec, mock_argv, mock_is_main, mock_watch, mock_wait):
   def test_main_exit_failure(self, mock_spec, mock_argv, mock_is_main, mock_watch, mock_wait):
```


&lt;Provide the same kind of information provided for Test 1>

**Coverage before:**

**Coverage after: **

The main function was initially 0% covered and then it improved to 90%. This is because of the 6 functions I created which comprehensively cover different scenarios, ensuring the main function handles modules, paths, syntax errors, uncaught exceptions, and exit statuses correctly.

<span style="text-decoration:underline;">Test 1: test_main_with_module</span> -> This test verifies the behavior when running a Python module using the -m flag.

<span style="text-decoration:underline;">Test 2: test_main_with_path</span> -> This test verifies the behavior when running a Python script directly.

<span style="text-decoration:underline;">Test 3: test_main_syntax_error</span> -> This test verifies the behavior when a syntax error occurs while running a script.

<span style="text-decoration:underline;">Test 4: test_main_uncaught_exception</span> -> This test verifies the behavior when an uncaught exception occurs while running a script.

<span style="text-decoration:underline;">Test 5: test_main_exit_success</span> -> This test verifies the behavior when the script exits successfully.

<span style="text-decoration:underline;">Test 6: test_main_exit_failure</span> -> This test verifies the behavior when the script exits with a failure status.

**Devansh**



1. Added tests in autoreload_test for **def start() **in autoreload.py

Coverage Results before:

Coverage Results after:

The function initially had a coverage of 0% and with the new test added, improved the function coverage to 80%. This is because we directly call the tests in order to handle various scenarios correctly within def start() mainly the if branches. The  test_watch_file and test_watch_directory tests are responsible for correctly adding files to watch lists (related to testing loop in def start). The tests_start_autoreload sets watching and autoreload_started flags to True which signifies the start of the function while test_io_loop_start helps by checking if start works correctly with a custom i/o loop.



2. **def test_stderr_supports_color(self)** in log_test 

Coverage Results before:

Coverage Results after:

We went from about 30% coverage to about 92% coverage by running test_stderr_supports_color(self) which utilises different conditions correctly to cover all the branches in stderr_supports_color. Using mocks and simulating isatty, we run a pseudo simulation of the function which checks the various scenarios with the various branches present in our function by setting either curses or colorama as true or both as false. 

**Pedro Escobin**



1. **def test_curl_create(self) **in curl_httpclient_test

Patch (diff) of the commit that shows the new enhanced test:



<p id="gdcalert14" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image14.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert15">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image14.png "image_tooltip")


Coverage Results before:



<p id="gdcalert15" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image15.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert16">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image15.png "image_tooltip")


Coverage Results after: 



<p id="gdcalert16" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image16.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert17">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image16.png "image_tooltip")
 

The function initially had a coverage of only 70% and with the new test added, improved the function coverage to 100%. This is because we directly call the function and to set the level of curl_log to logging.DEBUG. This satisfies the branch and executes the code underneath. 



2. **def test_curl_debug_logging(self)** in curl_httpclient_test.py

Patch (diff) of the commit that shows the new enhanced test:



<p id="gdcalert17" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image17.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert18">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image17.png "image_tooltip")


Coverage Results before:



<p id="gdcalert18" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image18.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert19">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image18.png "image_tooltip")


Coverage Results after: 



<p id="gdcalert19" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image19.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert20">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image19.png "image_tooltip")


The function initially had a coverage of 0% and with the new test added, improved the function coverage to 100%. This is because we directly call the function and satisfy the branches within the function. This satisfies the branch and executes the code underneath each branch. 

**Shubhra Mohan Singh**



1. **_reload**  in autoreload.py



<p id="gdcalert20" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image20.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert21">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image20.png "image_tooltip")




<p id="gdcalert21" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image21.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert22">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image21.png "image_tooltip")




<p id="gdcalert22" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image22.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert23">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image22.png "image_tooltip")




<p id="gdcalert23" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image23.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert24">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image23.png "image_tooltip")


Initial 3.33%. New 100%.  The coverage improved for this function because we start validating the behaviour of the function with our tests. An example is: test_no_execv function tests the _reload when _has_execv is set to False by initializing _original_argv and making the entry flag to False, calling _reload(), and asserting that subprocess.Popen and os._exit are called exactly once with the expected arguments, using @patch('tornado.autoreload.subprocess.Popen') to mock subprocess.Popen and @patch('tornado.autoreload.os._exit') to mock os._exit.

2. **_reload_on_update ** in autoreload.py



<p id="gdcalert24" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image24.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert25">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image24.png "image_tooltip")




<p id="gdcalert25" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image25.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert26">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image25.png "image_tooltip")




<p id="gdcalert26" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image26.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert27">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image26.png "image_tooltip")




<p id="gdcalert27" ><span style="color: red; font-weight: bold">>>>>>  gd2md-html alert: inline image link here (to images/image27.png). Store image on your image server and adjust path/filename/extension if necessary. </span><br>(<a href="#">Back to top</a>)(<a href="#gdcalert28">Next alert</a>)<br><span style="color: red; font-weight: bold">>>>>> </span></p>


![alt_text](images/image27.png "image_tooltip")


Initial: 4.35% New: 100%.  The coverage improved for this function because we start validating the behaviour of the function with our tests, such as reload_attempted sets the first flag to true, whereas it was false initially. Another example is the test_module_with_pyc_file function tests how _reload_on_update handles modules that have .pyc files by setting _reload_attempted to False, mocking process.task_id to return None, creating a mock ModuleType (test_mod) with a .pyc file path added to sys.modules, calling _reload_on_update, and verifying that _check_file is called with the corresponding .py file path.

**Overall**

Old Coverage Results: 



New Coverage Results:



**<span style="text-decoration:underline;">Statement of individual contributions</span>**

&lt;Write what each group member did>

Tanishq Gupta: 



* Instrumented the ‘_check_file’ and ‘main’ functions in ‘autoreload.py’ to gather coverage measurements. 
* Wrote and executed tests to cover the ‘_check_file’ and ‘main’ functions. 
* Documented the patches and coverage results for the instrumented functions. 
* Improved the coverage of the ‘_check_file’ function from 0% to 100% by creating four new tests. 
* Improved the coverage of the main function from 0% to 93% by creating six new tests. 

Devansh Maheshwari: 



* Instrumented the ‘_stderr_supports_color’ function in ‘log.py’ and the start function in ‘autoreload.py’ to gather coverage measurements. 
* Wrote and executed tests to cover the ‘_stderr_supports_color ‘and start functions. 
* Documented the patches and coverage results for the instrumented functions. 
* Improved the coverage of the ‘_stderr_supports_color‘ function from about 30% to 92% by creating comprehensive tests. 
* Improved the coverage of the start function from 0% to 80% by directly calling tests to cover different conditions. 

Pedro Escobin: 



* Instrumented the ‘_curl_create’ and ‘_curl_debug’ functions in ‘curl_httpclient.py’ to gather coverage measurements. 
* Wrote and executed tests to cover the ‘_curl_create’ and ‘_curl_debug’ functions. 
* Documented the patches and coverage results for the instrumented functions. 
* Improved the coverage of the ‘_curl_create function’ from 70% to 100%.
* Improved the coverage of the ‘_curl_debug function’ from 0% to 100%.

Shubhra Mohan Singh: 



* Instrumented the ‘_reload’ and ‘_reload_on_update’ functions in ‘autoreload.py’ to gather coverage measurements. 
* Wrote and executed tests to cover the ‘_reload’ and ‘_reload_on_update’ functions. 
* Documented the patches and coverage results for the instrumented functions. 
* Improved the coverage of the ‘_reload’ function by creating new tests. 
* Improved the coverage of the ‘_reload_on_update’ function by creating new tests. 
