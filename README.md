
**SEP Assignment 1**

**Team 72**

**Project Chosen**

**Name:** Tornado

**URL:** <https://github.com/tornadoweb/tornado>

**Number of Lines:** 36,634

**Tool used to count number of lines:** Lizard

**Programming Language:** Python

**Coverage Measurement**

**Existing tool**

The tool used to find the existing coverage of our chosen repository was coverage.py. To find the coverage of each file within the repository, we followed a few steps: 

1. Go to the repository's root directory.

2. Run this command in the terminal: **coverage run -m tornado.test.runtests (.coveragerc)**

3. Wait for the tests to finish and then run the next command: **coverage report.** This shows a quick overview of the coverage of the repository.

4. Run **coverage html.** Open the htmlcov folder and view index.html on the browser. This shows the coverage of each file and once a file is clicked, shows which lines are covered by the tests. 

**Note:** 

- When testing for changes and re-running the coverage, run **coverage erase** to reset the coverage then follow steps 1 to 4.

- Make sure to properly install all dependencies such as pycurl, running **pip install -r requirements.txt** does not work all the time. You can do this by running: pip install pycurl==7.45.3 for the specific version (required for cul\_hhtpclient).

**Coverage Results**

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXfZummHK2ZHZX7_NJ3KqdFM0pihuH98JlqElRzR22kC17yCtzbEtXnp2XEphN8YvPitQLO8dg-4L8pfhCHFesiHdHPstd6zP83QXHv3lO80alV93lq9qYTgTfBTXixGh9pO0Z1Gb8nKnl6UK0i5o78QEL4B?key=VOP6qdBBIo9ugIlHY77aOg)

**\*\*Note:** We output the instrumentation results to corresponding text files as functions are called many times during testing and clutter up the terminal. For example, the instrumentation results of the ‘\_reload’ function in the ‘autoreload.py’ file will be stored in ‘autoreload\_reload.txt’. To print the branches, we print the whole dictionary in the text file when the function is called.

**Your Own Coverage Tool**

**Tanishq Gupta**

**1.\__check\__file** in autoreload.py

\<Show a patch (diff) or a link to a commit made in your forked repository that shows the instrumented code to gather coverage measurements>

\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXfgrejFYT-w6UUtJ31aKvHc7tGddReY2-WB1llE6h6NyS6K3-XLxpBTGJ555xyfLVIESOqitGWyYmBd4sjJF51VpPPL_9kuug20oOTvkU83V6i-rynJHujwRMk1MCt0wEkUXwuWWsbT272omGYmugXuNTq0?key=VOP6qdBBIo9ugIlHY77aOg)

\<Provide a screenshot of the coverage results output by the instrumentation>

\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXfQ_aXYPNosXIVXnCpo9UPLePSGEPkeqQBiHF7GnaVwH3FbXiTuOfBwbsQvA93dY2hXQ5UA1aSMAic4QpHzyaMX_9vKpwkz10wDcmjit1uQj61-9Uu7H4XVtWNg2wp8VTm0BQACtoaTn4Ewm8LnTzD9n5M?key=VOP6qdBBIo9ugIlHY77aOg)

**2. main** in autoreload.py

\<Provide the same kind of information provided for Function 1>

\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXfnLX4J3mYZgr98mREo_43-tDx7Tfn8Z4gGZWc9b6FHCOEJn0ALNTDZAbSqhJZg9IHnj7pjz2YGrliU1tK1274iy2wYVpGic5nVoZwTRmq-CyrLR_XC7zMMm8HOMC9PNoc6LlUa6x4uYslLJzsjwEylLy_C?key=VOP6qdBBIo9ugIlHY77aOg)

********![](https://lh7-us.googleusercontent.com/docsz/AD_4nXe7op42LapfxDzIF-j7JvUDak49zZVZFSvoekn3qzStkaNXHnBoXlf2cKG1RUqtO-2Jv0GU0DKZLmkaQ9d2mc3MKe-c6jnHUI4d8A89xnbM73j3r9P2iWHRruLUZ0Xj8vNDN4ENohhRtSZeGsJXbb3ql-jG?key=VOP6qdBBIo9ugIlHY77aOg)

\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXc9cvkLK5itq3mLUDC1mz5QX3rk3qoiIbnayppdKmz9KRabJUE5sFpCgbksRd1KegtQFFjIOwuWb6Z7WWFZmippWHwWqCZH7RBGUw9T9cT_jqdX27SK1-Uk7aNhdUGYaa4eoU-LAV2xUu1_RrjytirDupAG?key=VOP6qdBBIo9ugIlHY77aOg)

**Devansh**

1. **def \_stderr\_supports\_color()** in log.py

\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXfhucKbjl3jq9rtUDgADbwikyaD-IZJG_a2SNwLiA0ZwyYqKFrLgtl6_1dLVGvaF-Zf6H5IxPWJH3yK62VhT24-rxRNHLAX0SBMg7bdWgppK4LMyyyAPsUkntxB0Xk3BACsuAEBscoYucWaIVKbBn1uzY_X?key=VOP6qdBBIo9ugIlHY77aOg)

Coverage results of our own coverage tool:

\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXcv-nWy7K0-or0nUlmYUty0vONcc-65Dt-2Xinwy8c_xHnEJPftviQ2GWht7DwEQpN170NXzJvOcYOGS7hwGEUO2fO_31San5Vv9uj1CjRyIU-mQiHIBYAT3buC8aqFeATHHtA7mqv-gYOHiGzF3RzoF-t8?key=VOP6qdBBIo9ugIlHY77aOg)

2. **def start()**  in autoreload.py

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXdenx4VhZkWMggGvw7n_Z71Lzc9tAdUxLOFSnG_1wRX8FLPrP0TR0xjZkxUzjnE_QM7Gout8I38enu5ESqfKivVb2rDQqlbzWkS74LLONlGIsFV4VzHJE8CCIQ7mGi7nE24uKCVSIf7NxWpUDdwJRDtUUiu?key=VOP6qdBBIo9ugIlHY77aOg)![](https://lh7-us.googleusercontent.com/docsz/AD_4nXc6r53bgkotuhgQjwQ3IrIw61XQJKogw4FDqWnGq42PF-q2DAFVEPw0RzkS2beHlE_ba9hTvOaN8Dx6I_VUyY96w2R8_ygzCnNb7OEZ5T8ny6w7tg95X68DB5Q6T5RPccopjX0QXdtc9t9Rv4M1B1BsxIyC?key=VOP6qdBBIo9ugIlHY77aOg)

Coverage results of our own coverage tool:

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXf3yLbV4mtR7eROTPNWIOk3j_ZiPDy-8y4NgqHvlVbX8Uqu6_nqge7pppr1YKb_odN1G3RUz9dy3PtLS76z_3IL3lYCvYgw9gxn_6S7hNHNOq7rmD5yE52vKlbO5K-OwXE7b9xDc-W7kN60w2HxO0nSuTmT?key=VOP6qdBBIo9ugIlHY77aOg)

**Pedro Escobin**

1. **def \_curl\_create(self)** in curl\_httpclient.py

Patch (diff) of the commit that shows the instrumented code: 

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXekimbcUOjd_bPYcp5TFn2XjOU92Qfcq2oVaAT99e7AQQqkmfDkf8eAeNwCKFCv2oa06vFLJBxQw_GFOjI_MQAT9sre-bnsoTQPyUC6GXZspKRcu_6rAbgba-7fdDhBYBtbh2kC5lLh_rtryYzxmGu5FP8?key=VOP6qdBBIo9ugIlHY77aOg)

Coverage results of our own coverage tool: 

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXfrOD8yEB7xQpuoxZnn9osp9gmMLcHrCW0ge5ehZKH53ZGguSA0uDU4TA33OOgGMW0zuuqyuWICl7YNZiwvPw0S-wDihsa_Ab8okq6PJD_aFAcZFhmkY2Ig8CMyuoJJerBUUM21yt-3AhiPYjwk-gPDKs4?key=VOP6qdBBIo9ugIlHY77aOg)

2. **def \_curl\_debug(self, debug\_type: int, debug\_msg: str) -> None** in curl\_httpclient.py

Patch (diff) of the commit that shows the instrumented code: 

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXdY0-VMYbvwl-9KlSR2lFnQ81VZ-b9alJWxV-s9kiRr_hkrj1cH-lYK1QZwowqyIIFx5s3OlMIJkfO6i6IH7KC8G2zqEzimIdOwmR9ogR3svECpdhu4dkqQ3MN2TKX51dq7nSGPcnXW-QAIP50_kOlsmi0?key=VOP6qdBBIo9ugIlHY77aOg)

Coverage results of our own coverage tool: 

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXfsPbKV5Sv_FZrvFL426QmZAn6Ff62VzUPazE5Z6Wfy9D6OmgM8lACbQMjdRlnxmLTHpmPM1_hOsq3WG5POwMpr6gbX0oasJkeegpzXSKneEg1NrPErLlHAvs0O6ZXfgeTTu9z5M_KoPn1IuFeRt2rt-mHb?key=VOP6qdBBIo9ugIlHY77aOg)

**Shubhra Mohan Singh**

1. **\_reload**  in autoreload.py

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXdMqLw59KVhF5XubemdxiRtx_LYrjeUvmPR_9W9-WNAxgxH6hMk8Q1EuSeVONRiDnMmVMKOIsFC0i9OaiRI9GRlIyx1N4vFTY352Vcea_VHb_e5thWHF2F9WkpnCiqLXQ023HKoOUeTumA5NTMR2ndytNHA?key=VOP6qdBBIo9ugIlHY77aOg)

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXdr37YYOvPjsnmHAob87VuDHbbikyAlc_d2mhraugZzsXpeN40jQ9xzdwQDR4RBbXcFYN3Lb6hMXrVDNVz_8rqo0FZtW4dDJu1uZo1889c6DjEdfoGBiwz9MDxxhIysoUUsa2Dv-mp_52y8VzPHF4amyakq?key=VOP6qdBBIo9ugIlHY77aOg)

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXci6b28qZ_2ZNYm5e1nhlQkD_Ta8dErhDuEVi99S0w4gtkSHtsJ9eN6JYFzGGNCGPIY1YKOhg5HsVdD2ABcLuC0-7Vwbinx5-Rt-g2QddzOr_tNGDWsVJzKS7Ot6dE_WHI2-KR2ShG_RM81a4vDLupPwR4?key=VOP6qdBBIo9ugIlHY77aOg)

2. **\_reload\_on\_update**  in autoreload.py

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXeLp7RlVAS7Zrcd0vlIp2kwl2fhwo8-_wuZixVXycqGboSK5UNx1w1SLsnDe4I1zsbL2eof0RLuTk4r9pCgK5Ye6ldbeXPC2ksCXwcK4AhHPxOhV8rTqO5dlXSGK-SSVpu-mz-fw6i8M_lGd0YB6gu56BHW?key=VOP6qdBBIo9ugIlHY77aOg)

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXeyykaQla03ZpD2iirbMePyfkwPx0mj22QUUrS0iPsBT_7-H3J7t976MbsQeg4tZw45s4ciuOQxaXzTp0ayYOfTKPc5WSLG7GZ1aspD5P4Hlvvc9n1EgKcigLF0YCgLytitaBHggpwoFW1gDfHY-Ev92mgQ?key=VOP6qdBBIo9ugIlHY77aOg)

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXcncwVWLHxebJpp47O5y7xXZctJY3JRUfQZSN-zaWxH9LtJ835MQ7LcGRAeFdam7qppO36ZkgCAQ9uCR_GcG3rWhGWz9KcrSByRREZxoh54kWQC-g8Wu1G4V5mnK9MIVL0CHsU4qWwlHhfNMZoyuIFkJcbK?key=VOP6qdBBIo9ugIlHY77aOg)

********

**Coverage improvement**

**Individual tests**

**Tanishq Gupta**

**Tests to cover the \_check\_file function,**

    def test_file_stat_exception(self, mock_stat):
    def test_file_not_in_modify_times(self, mock_stat):
    def test_file_in_modify_times_no_change(self, mock_stat):
    def test_file_in_modify_times_with_change(self, mock_reload, mock_log, mock_stat):

\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXeEqNIOEbHKE5AhQtlhvFI_MfcwLxNebNy4Zzixwsn50OC4aYnX-1PAsmnB7eFlxokzrevS_WhvJgMrU_V3jaGGRS1fik2pSc0zhWtOdk0ke-cmyEn2XWlYHEtylWMiDcC5C6oqPrzf5K-vYiGP4tEDPW5A?key=VOP6qdBBIo9ugIlHY77aOg)

\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXfZ6X8lqFy6uRifT400a8LwISW3ARG1s5wwq5KwyjYzS2u83WBK5SQWxaYh3psw361SWsfw10m8ajpgjCSJSeLUthvIos1AoYnXQYinoncnRRxCUqZp_TYazFacKdHegXNpnsMQ1pA2D-AsJ7ORfjXdhstd?key=VOP6qdBBIo9ugIlHY77aOg)

\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXd_uOHdhAJ6xlKDb7h1Ff4rP7AYnQBq2l8NcYV1JT_CchdtNht4E5G40kg_Wrdm9hr5icZIUaJtRMlbky6JYqKJYrzdvvpzBI8OUmlsWzDa57OoOLWhwAjKHdkK1IYvNqTwrcqUX_VuWeDDQM-5_woCQzW3?key=VOP6qdBBIo9ugIlHY77aOg)

The \_check\_file function was initially 0% covered and then it improved to 100%. This is because of the 4 functions I created which ensure that the \_check\_file function handles various scenarios correctly, such as exceptions during file checks, new files, unchanged files, and modified files, ensuring the appropriate actions are taken in each case.

Test 1: test\_file\_stat\_exception -> This test checks the behavior when an exception occurs while trying to get the file status.

Test 2: test\_file\_not\_in\_modify\_times -> This test verifies the behavior when a new file is checked for the first time.

Test 3: test\_file\_in\_modify\_times\_no\_change -> This test verifies the behavior when a file’s modification time has not changed since the last check.

Test 4: test\_file\_in\_modify\_times\_with\_change -> This test verifies the behavior when a file’s modification time has changed since the last check, and the server needs to be restarted.

**Tests to cover the main function,**

    def test_main_with_module(self, mock_spec, mock_argv, mock_is_main, mock_watch, mock_wait):
       def test_main_with_path(self, mock_spec, mock_argv, mock_is_main, mock_watch, mock_wait):
       def test_main_syntax_error(self, mock_spec, mock_argv, mock_is_main, mock_watch, mock_wait):
       def test_main_uncaught_exception(self, mock_spec, mock_argv, mock_is_main, mock_watch, mock_wait):
       def test_main_exit_success(self, mock_spec, mock_argv, mock_is_main, mock_watch, mock_wait):
       def test_main_exit_failure(self, mock_spec, mock_argv, mock_is_main, mock_watch, mock_wait):

\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXdkEcXtQPB84qkWaekLvr67AHswGy7PUANUuQAvk8zOEjT07qCJoiRpqLGOjw9YPDAqr2Y5q5utClK9kFqK-e3ovT9jfOwPRCMLNMROsZRtiqg4UBJc6D4QchTX38-H01BD93yX-ykX_ISmnJsk2lU1cU9d?key=VOP6qdBBIo9ugIlHY77aOg)

**Coverage before:**![](https://lh7-us.googleusercontent.com/docsz/AD_4nXdyz5082-eIe15GJ9AvA_ifP6xiiqKzRCuJn0pvAi3slNGE_QbsT3OWcdEk2jm-HzGjk6OGQ2SfUVKBLKENH0FBsZVX4WFglt0aCA--dc4RWw2g6WV4yAfDTkAG7gU-muql7xgSzrlY6WU0xs4tK6KCpQrA?key=VOP6qdBBIo9ugIlHY77aOg)

\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXcC9moymdxSygQb_agOBZQyk5OTyBRaum33mTa_3h43DGkbJu7mQIzF9tvzJ6tfX6hxhU1sznZgu5yY17tYbrm4qVmEjFd08DlmIezhEAeDq8TbA1uclV5DQFETGKSF5Y46zTyh-Z4PCntKQXH9iNuZuKBk?key=VOP6qdBBIo9ugIlHY77aOg)

**Coverage after:** 

\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXfdc0CTuSUD-F4rNTTpfsNJMoGQTCV6qS9knY6rqeu-fU_2VD7bHuY35_YPJnLVCCEBTzjN2KxSmvG0WQgIyVx_eScxfJTBtyJNElglSuYhgFwByDYe21rHPz_Rk3x_GG9SWfHfAAlbn4GKfRa-UIREX50X?key=VOP6qdBBIo9ugIlHY77aOg)\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXfS3Y2kIhAvkUZmghop3rI0Cuw7c2Yc9y-Sir5Ai4slvu51xoZQN6DTKGZGRnla8OjoX-3eJUJdFcj55NnvwK4gqXLJiLNnB9U4GTBvh4KxTEQBejgVcmSSRZZZrBeycpA8Yqfcfaeu3GOwtYfPWFXIshhh?key=VOP6qdBBIo9ugIlHY77aOg)\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXfm_X8nYTYCmbYRmVoqYHctLsv1ybi4Ww6h8aaOPH8uDzYOYDGKxmqRTDHjjrkG5npyB5dmHMS4bAL8e8_AO73JB9x9EqIU1McLW08IP_7yNydLlCMRmdMb93xCCfLlR-gB050upDtwLv59J3UrBOlKjwnC?key=VOP6qdBBIo9ugIlHY77aOg)

The main function was initially 0% covered and then it improved to 90%. This is because of the 6 functions I created which comprehensively cover different scenarios, ensuring the main function handles modules, paths, syntax errors, uncaught exceptions, and exit statuses correctly.

Test 1: test\_main\_with\_module -> This test verifies the behavior when running a Python module using the -m flag.

Test 2: test\_main\_with\_path -> This test verifies the behavior when running a Python script directly.

Test 3: test\_main\_syntax\_error -> This test verifies the behavior when a syntax error occurs while running a script.

Test 4: test\_main\_uncaught\_exception -> This test verifies the behavior when an uncaught exception occurs while running a script.

Test 5: test\_main\_exit\_success -> This test verifies the behavior when the script exits successfully.

Test 6: test\_main\_exit\_failure -> This test verifies the behavior when the script exits with a failure status.

**Devansh**

1. Added tests in autoreload\_test for **def start()** in autoreload.py

Coverage Results before:![](https://lh7-us.googleusercontent.com/docsz/AD_4nXdLmWp2GlONJH57piZP80lD9U5FWcMC6CskUJ6g59pK3oWqiqNqmcjs4VHTDrRLJ8vYh3qGl9Q0GF07MR12dUffHjHI4DFyzZI05RnVW9iolmEC0Ij3lR0aYtFGnExR0VJht7prXW9Fn0amhNZxb44cDrKx?key=VOP6qdBBIo9ugIlHY77aOg)

\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXcnHUZoV9whzG5xE5Ch0kJEzDAJz9BQ5d9klAK61jIKhzcoGjUcduNh3ql9eMFSJp8yResC9luT-0vbEM0RXgNVGv_Zp1JtcL0bjvpaWhJpXGuGJa5J8EfFE7-HqVJebC7R4m5gki3_gzSF9xwbQRmAQ2dl?key=VOP6qdBBIo9ugIlHY77aOg)

Coverage Results after:

\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXej2-ctHFy_-aXPnXHe3pHvrcedpTOk3mszu2slt29-ZPIofgGLkftichpr512MXwlTm72Bl8tvVicSsxktxd0zt97stkBcxvQ05nucPEYVE32TTgsX_3RMnXmJZqoYzfTa3lU587qa4hkTLspst4WMd5xR?key=VOP6qdBBIo9ugIlHY77aOg)

The function initially had a coverage of 0% and with the new test added, improved the function coverage to 80%. This is because we directly call the tests in order to handle various scenarios correctly within def start() mainly the if branches. The  test\_watch\_file and test\_watch\_directory tests are responsible for correctly adding files to watch lists (related to testing loop in def start). The tests\_start\_autoreload sets watching and autoreload\_started flags to True which signifies the start of the function while test\_io\_loop\_start helps by checking if start works correctly with a custom i/o loop.

2. **def test\_stderr\_supports\_color(self)** in log\_test 

\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXcXa_9P34EdTsDWjJ4LvUg_7YVsEs735hT5t3DL4BwCAUfdMoLLFQUNngUD_03Nj7twI5xJvIIPZmX8d2L7scR7POpv0coTT9Khv0s5X7uQ0U1ZcOPQy9f4Y5q0kcmgeygZnc_DG5K_MUGdH2p6pPnHz-g?key=VOP6qdBBIo9ugIlHY77aOg)

Coverage Results before:

Coverage Results after:![](https://lh7-us.googleusercontent.com/docsz/AD_4nXc9K5sk74z4ynHpoDRajSJb2GUmphYh3_zak9Af36XOkO1vtCUue8yTaMpVeJ6d6y2AgYNK76r51Q9JrLIzILkrpsCTq8NJ0P1wcXmt5MGllwUGnIXEo4hSvM5VsY5XJ67AXv_A4Os4icmKOvJZ9WMWjG5i?key=VOP6qdBBIo9ugIlHY77aOg)

\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXeEHQV30GaY2QCxerw8e61LmtU0vXJFApc65pycr-53PsA-gqgXGAhBFwMGYd_QybPmYz8rBCek-pgCp7P8Yb4rezjgDQfwl26zTvTiBMMefpof1-gGkhYYeT4RWGXsAidEkdfOR8UqmFMGLqCBKcJLvm3p?key=VOP6qdBBIo9ugIlHY77aOg)

We went from about 30% coverage to about 92% coverage by running test\_stderr\_supports\_color(self) which utilises different conditions correctly to cover all the branches in stderr\_supports\_color. Using mocks and simulating isatty, we run a pseudo simulation of the function which checks the various scenarios with the various branches present in our function by setting either curses or colorama as true or both as false. 

**Pedro Escobin**

1. **def test\_curl\_create(self)** in curl\_httpclient\_test

Patch (diff) of the commit that shows the new enhanced test:

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXedG8hdZc-zuZlWwQNPeH15JDD45UZVOf-n1pCkq9CaEDeu6OTrOTjs0elErINkJ5qd9AsWzp3cwvbNsN1HUF2s_luizZmn-H5TmDlcPolW_JgQCWuNk0dgXYsOG8oLiC3XNe1qY7p8sKF1xHTCoKnMwXjR?key=VOP6qdBBIo9ugIlHY77aOg)

Coverage Results before:

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXcHKW2QJoG-PDVrXEZcW6WDe4_kI8BRDWyJSZ1MS52QtNhWcamOVfayq_CinY3XdEtzg4OP25gcnTaSgNQSfH9Y8oE28qrhR9eeoX50HTUlsjBzQ1WZknCEHPwOQs5xQxIgnwT04g65D9FKXhPggdXumGeE?key=VOP6qdBBIo9ugIlHY77aOg)

Coverage Results after: 

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXdJktXSZFmzgT9Dnbrm1E__kXllPFWR9whwjnA0wt3DUev_JQM9DfyR8aIBL1VkFk39_YZZD_DHlxHJdcmQCBy1ykJz5Jsa41sKH5ScM6KoJVMcxcEyLspPKuaHI3qX-Lz2ndodqvvoFhzybUQnj1B6cCw?key=VOP6qdBBIo9ugIlHY77aOg) 

The function initially had a coverage of only 70% and with the new test added, improved the function coverage to 100%. This is because we directly call the function and to set the level of curl\_log to logging.DEBUG. This satisfies the branch and executes the code underneath. 

2. **def test\_curl\_debug\_logging(self)** in curl\_httpclient\_test.py

Patch (diff) of the commit that shows the new enhanced test:

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXfi-uyQKH9navnJjNuQAOQTn7yTVezGzgRTFzqrqJqv9Icw4mrPCHwTruYo6mEkoWRMwIwnSYStCkwq3StXsMFS963M0BPLnALA-ANKvF7pwR2SKrVouQwbsFjfDi59ZfwnLnRKNeePoApNfFW4G7ZBGAI?key=VOP6qdBBIo9ugIlHY77aOg)

Coverage Results before:

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXcyy7_XyUwV4V9mR4sEgkP3Tu8Xkffplbrmp2nV_f6PbRI3cVHd8aMQ5gB7qPUBC0njV2NpZRaZgLoMiRyYIaDU2dKnnZfI-PCL0LlfqGWY4HfEsxXteE6CSNf94hpX-VfpE7ih1aaJdKpSvtiP9O2ZL6xq?key=VOP6qdBBIo9ugIlHY77aOg)

Coverage Results after: 

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXc6sN3imMobMNgUShoUtnyLeDk86gYlvEQPlamZZN8o5aBWFtvQL3z8qDX4n0FAKtHDi1TOYskvyfeQhi6-OW-IPnoAQh1vzrlXPr5c2cYiuw6WaUE2do945EtP38QEO17lGFTlJiVSCYH0owEjfjQZAXF1?key=VOP6qdBBIo9ugIlHY77aOg)

The function initially had a coverage of 0% and with the new test added, improved the function coverage to 100%. This is because we directly call the function and satisfy the branches within the function. This satisfies the branch and executes the code underneath each branch. 

**Shubhra Mohan Singh**

1. **\_reload**  in autoreload.py

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXeIimTJXpfnHKhX4DLK9fl-k4OwFn3mupd2Mn6By4rCpjYOR6ket-n6ZyGlbdHoofUKc_HM5q1-UobI_32jSmEG699H_Fbuyn4FJlEhXVLYhDzIGVaWAFmU6gyJclditjj8f6vqKgntdMwGOdBdotGV320?key=VOP6qdBBIo9ugIlHY77aOg)

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXccZ7sN1XTbCrcurve3bYkZGUOn4YXcxw9yUWMdJxuVU3XdApKVpsbg8rzO5JsBQIKebjdEAolSy_wVRQGOWVtuWpuo6jWGBnFng09nYX7rOejQywIsRza_lOCQ9baDB9eimou6wgjNLs02RZjR-k9nXw7F?key=VOP6qdBBIo9ugIlHY77aOg)

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXd69QXSAeFslBiTun3Ws6SxOz7e5uL95LERDQRfBpXjtbMSRMgUTAdNlcoTUcI41wlDglBcOHZ4EMZ2GABS0OwNnFY7fmApwyKjBO1VG6Hd0SLufe9IqrT4smZPppgWg0712prn8HaMRHx2XWH-siIBNxJy?key=VOP6qdBBIo9ugIlHY77aOg)

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXdY5ENbwApsk1UZcGb5PRtEyIYnafNshV8dJzYRSc41bPlgV1hSnc4T_mVX9XWcBn30Pzr093IfQmQ_uclzewaCfv1YR9LBFuyIrQjJOaxv4KTU7c0cm6p8PwwBj48tsgsNbDdf3Mpal1MrowyVFUJMyAo?key=VOP6qdBBIo9ugIlHY77aOg)

Initial 3.33%. New 100%.  The coverage improved for this function because we start validating the behaviour of the function with our tests. An example is: test\_no\_execv function tests the \_reload when \_has\_execv is set to False by initializing \_original\_argv and making the entry flag to False, calling \_reload(), and asserting that subprocess.Popen and os.\_exit are called exactly once with the expected arguments, using @patch('tornado.autoreload.subprocess.Popen') to mock subprocess.Popen and @patch('tornado.autoreload.os.\_exit') to mock os.\_exit.

2\. **\_reload\_on\_update**  in autoreload.py

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXcNe3QpaNHru8uFzPIL9HodIDZMCPPxs-Jv60xeiLmgTwOamqgS01CA2PvYoGYsa7CWYHI6QjL75AC3kKVoa68uROsChcnjgMYJwG3IvOloca6FI-CFKInVN6I7ube0NVN_VeJBxZ6gWyF5CpPsjoznTR4?key=VOP6qdBBIo9ugIlHY77aOg)

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXdvfl3_DaIE3b7qoSvHU335kUmACQGcMSs-uvXhGblTFjH9g0Nehg22FV8f9t3SGJOSng2awVJKfkscYoTjuNA0rgX-LrWlUMsABP4m22l50CLcek8UKsfYxBYwxUl6UloecuPv9ic2fSctDtNkX1_fCcw?key=VOP6qdBBIo9ugIlHY77aOg)

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXduRZ_9u-T5hmbjfoFXUJjATq_sosqlXc32DOH9LQfzVVRGvDd66ndN1G4taP22K_B2mBb3RJ54SunG_13ddmEPGU0M-dfkyR5exlleNHtO9mabdGguLhsI_0vSAT_cv-p20RzPLfjfF3qSvkNh5y8-j_e1?key=VOP6qdBBIo9ugIlHY77aOg)

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXfHN7GKYB8lR-JOo6EVK7b7NraW9rN3weJW6fALPTZKYZaiOYa1eUIHznvhLFblnC9IA7__82DmEzVcDWiSVIPaRsCGjdvzAizH7FodtN2qYFjTAed3c_CTpdl7-K_ouXz39MBrbJZ_rXYMJIm7uBd6i-nB?key=VOP6qdBBIo9ugIlHY77aOg)

Initial: 4.35% New: 100%.  The coverage improved for this function because we start validating the behaviour of the function with our tests, such as reload\_attempted sets the first flag to true, whereas it was false initially. Another example is the test\_module\_with\_pyc\_file function tests how \_reload\_on\_update handles modules that have .pyc files by setting \_reload\_attempted to False, mocking process.task\_id to return None, creating a mock ModuleType (test\_mod) with a .pyc file path added to sys.modules, calling \_reload\_on\_update, and verifying that \_check\_file is called with the corresponding .py file path.

**Overall**

Old Coverage Results: 

![](https://lh7-us.googleusercontent.com/docsz/AD_4nXdIn1T4HQq3JoBC_khD_AfOdaNeC4wMiWaEOWUakts28IqLSaRD8BpK_IBkYUpHp-djqO2rlMFbLgu8cAuNe-iJuF2eb3rzfTrcTFh51px-TRo1yiCxIbtY3wquqdquq76liinkY-k1XP7-Clrt6WndxgPe?key=VOP6qdBBIo9ugIlHY77aOg)

New Coverage Results:

\
![](https://lh7-us.googleusercontent.com/docsz/AD_4nXeZZDuCwHf0wS6a5AMVLlAuBEg-dUQkbwdmCmuKxE8lYmjhCFt8gYc04SBQpVKUUR91RjmNjtosezOAXpbGWCawqWASghkUmnfnILyQfPzEBXQaSV5i32vOYfVhf36nA3aYWkpEZDAjxBsOVD_6K1q_3EGD?key=VOP6qdBBIo9ugIlHY77aOg)

********

**Statement of individual contributions**

\<Write what each group member did>

Tanishq Gupta: 

- Instrumented the ‘\_check\_file’ and ‘main’ functions in ‘autoreload.py’ to gather coverage measurements. 

- Wrote and executed tests to cover the ‘\_check\_file’ and ‘main’ functions. 

- Documented the patches and coverage results for the instrumented functions. 

- Improved the coverage of the ‘\_check\_file’ function from 0% to 100% by creating four new tests. 

- Improved the coverage of the main function from 0% to 93% by creating six new tests. 

Devansh Maheshwari: 

- Instrumented the ‘\_stderr\_supports\_color’ function in ‘log.py’ and the start function in ‘autoreload.py’ to gather coverage measurements. 

- Wrote and executed tests to cover the ‘\_stderr\_supports\_color ‘and start functions. 

- Documented the patches and coverage results for the instrumented functions. 

- Improved the coverage of the ‘\_stderr\_supports\_color‘ function from about 30% to 92% by creating comprehensive tests. 

- Improved the coverage of the start function from 0% to 80% by directly calling tests to cover different conditions. 

Pedro Escobin: 

- Instrumented the ‘\_curl\_create’ and ‘\_curl\_debug’ functions in ‘curl\_httpclient.py’ to gather coverage measurements. 

- Wrote and executed tests to cover the ‘\_curl\_create’ and ‘\_curl\_debug’ functions. 

- Documented the patches and coverage results for the instrumented functions. 

- Improved the coverage of the ‘\_curl\_create function’ from 70% to 100%.

- Improved the coverage of the ‘\_curl\_debug function’ from 0% to 100%.

Shubhra Mohan Singh: 

- Instrumented the ‘\_reload’ and ‘\_reload\_on\_update’ functions in ‘autoreload.py’ to gather coverage measurements. 

- Wrote and executed tests to cover the ‘\_reload’ and ‘\_reload\_on\_update’ functions. 

- Documented the patches and coverage results for the instrumented functions. 

- Improved the coverage of the ‘\_reload’ function by creating new tests. 

- Improved the coverage of the ‘\_reload\_on\_update’ function by creating new tests. 
