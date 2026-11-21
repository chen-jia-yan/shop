# 報錯信息匯總
Wednesday, November 11, 2026  10:26 PM

1.
Fund Switching (COM 2 Bermuda) window wait successPassed: Job submitted. (Ref:0127056)finding transaction windowtrans_status:COMPLETED

2.
Add booster/PDF (COM 2 Bermuda) window wait success

Exception: Job submitted failed, pop-up error: During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 567, in _wrap
SystemExit: 0

3.
Fund Allocation (COM 2 Bermuda) window wait success

Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 174, in test_03
_TC_LAS_FundAllocation_01 File "system_view\LAS_view\las_functions_page.py", line 1681, in las_fund_allocation AttributeError: 'bool' object has no attribute 'type_keys' During handling
of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591, in run File
"unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 567, in _wrap SystemExit: 0

4.
Add booster/PDF (COM 2 Bermuda) window wait success

Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 203, in test_04_TC_LAS_ADD_PDA_01
File "system_view\LAS_view\las_functions_page.py", line 2042, in las_add_pdf File "pywinauto\base_wrapper.py", line 937, in type_keys File "pywinauto\base_wrapper.py", line 680, in
verify_actionable File "pywinauto\base_wrapper.py", line 703, in verify_visible pywinauto.base_wrapper.ElementNotVisible During handling of the above exception, another exception
occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod
File "common\BeautifulReport\BeautifulReport.py", line 567, in _wrap SystemExit: 0

5.
Traditional Partial Surrender (COM 2 Bermuda) window wait success sum_assured:6267705 new_sum_assured:6205027 Passed: Job submitted! finding transaction window

Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 233, in test_05
_TC_LAS_TraditionalPartialSurrender_01 File "system_view\LAS_view\las_functions_page.py", line 2171, in las_traditional_partial_surrender File "system_view\LAS_view
\las_functions_page.py", line 208, in las_transaction_log File "base_view\win_base_view.py", line 211, in win_set_text File "pywinauto\application.py", line 379, in _getattr_ File
"pywinauto\application.py", line 250, in _resolve_control File "pywinauto\timings.py", line 436, in wait_until_passes File "pywinauto\application.py", line 222, in _get_ctrl File
"pywinauto\findwindows.py", line 98, in find_element pywinauto.findwindows.ElementAmbiguousError: There are 3 elements that match the criteria {'best_match': 'PolicyEdit',
'top_level_only': False, 'parent': '', 'backend': 'win32'} During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59,
in testPartExecutor File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 567, in _wrap
SystemExit: 0

6.
Reinstatement (COM 2 Bermuda) window wait success

Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 262, in test_06_TC_LAS_Reinstatement_
01 File "system_view\LAS_view\las_functions_page.py", line 1127, in las_reinstatement AttributeError: 'bool' object has no attribute 'type_keys' During handling of the above exception,
another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in
_callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 567, in _wrap SystemExit: 0

7.
Partial Surrender/Terminate fund rider (COM 2 Bermuda) window wait success no Microsoft .NET Framework window

Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 289, in test_08
_TC_LAS_PartialSurrender_01 File "system_view\LAS_view\las_functions_page.py", line 1931, in las_partial_surrender File "base_view\win_base_view.py", line 655, in handle_popups
Exception: Job submitted failed, pop-up error: saveParSurrRecord 1:Transaction failed: A transport-level error has occurred when sending the request to the server. (provider: TCP Provider,
error: 0 - An existing connection was forcibly closed by the remote host.) During handling of the above exception, another exception occurred: Traceback (most recent call last): File
"unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line
567, in _wrap SystemExit: 0

8.
Payment/Transfer Value (COM 2 Bermuda) window wait success1Passed: Job submitted. (Ref:0430007)finding transaction windowtrans_status:COMPLETED

9.
finding transaction window Client Bank and Mandate Approval (COM 2 Bermuda) window wait success

Traceback (most recent call last): File "system_view\LAS_view\las_functions_page.py", line 899, in las_add_card TypeError: 'NoneType' object is not subscriptable During handling of the
above exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py",
line 386, in test_11_TC_Billing_Change_Monthly File "system_view\LAS_view\las_functions_page.py", line 938, in las_billing_change File "system_view\LAS_view\las_functions_page.py",
line 4286, in las_add_card Exception: Add DDA/CCD Error! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59,
in testPartExecutor File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 567, in _wrap SystemExit: 0

10.
finding transaction window Billing Change (COM 2 Bermuda) window wait success

Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 468, in test_12
_TC_Billing_Change_Half_Annually File "system_view\LAS_view\las_functions_page.py", line 4411, in las_billing_change File "base_view\win_base_view.py", line 655, in handle_popups
Exception: Job submitted failed, pop-up error: Cannot get MSP Config During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\
case.py", line 59, in testPartExecutor File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line
567, in _wrap SystemExit: 0

11.
Billing Change (COM 2 Bermuda) window wait successPassed: Job submitted. (Ref:0144117)Transaction Log / Policy Notes window wait successtransaction COMPLETED, summary
information is: ['Billing Change', '10/30/2026 10:56 PM', 'COMPLETED', 'Prm Paying', 'Jan 23, 2026', '', '', '43153.10', 'Annually', 'Annually', 'Cash', 'Cash', 'Jan 23, 2025', '23', '23']

12.
Premium Holiday (COM 2 Bermuda) window wait successJob submitted. (Ref:0059051)finding transaction windowtrans_status:COMPLETED

13.
Premium Holiday (COM 2 Bermuda) window wait successIf policy with reg cont, pls remember goes to coverage maintenance update the reg cont premiumRecord Submitted. Letter will be
print out during EODJob submitted. (Ref:0059052)finding transaction windowtrans_status:COMPLETED

14.
Full Contract Reversal (COM 2 Bermuda) window wait success Reversal succeeded. finding transaction window

Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 657, in test_17
_TC_LAS_FullContractReversal_01 File "system_view\LAS_view\las_functions_page.py", line 1326, in las_full_contact_reversal File "system_view\LAS_view\las_functions_page.py", line
210, in las_transaction_log File "base_view\win_base_view.py", line 248, in win_select_option File "pywinauto\controls\win32_controls.py", line 415, in select File "pywinauto\controls
\win32_controls.py", line 364, in _get_item_index ValueError: 'Reversal' is not in list During handling of the above exception, another exception occurred: Traceback (most recent call last): File
"unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line
567, in _wrap SystemExit: 0

15.
GetCapsilPolicyNo & GetPolicyNoteByPolicy :get policy note by Policy error: A transport-level error has occurred when sending the request to the server. (provider: TCP Provider, error: 0 -
An existing connection was forcibly closed by the remote host.)Change Agent on Coverage (COM 2 Bermuda) window wait successPassed: Job submitted.finding transaction
windowtrans_status:COMPLETED

16.
11/30/2026Service Fee (COM 2 Bermuda) window wait successfinding transaction windowtrans_status:COMPLETED

17.
7/30/2024 Service Fee (COM 2 Bermuda) window wait success finding transaction window

Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 743, in test_21
_TC_LAS_ServiceFee_termination_01 File "system_view\LAS_view\las_functions_page.py", line 1110, in las_service_fee_termination File "system_view\LAS_view\las_functions_page.py",
line 208, in las_transaction_log File "base_view\win_base_view.py", line 213, in win_set_text Exception: Can't find window Transaction Log / Policy Notes (COM 2 Bermuda) During
handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591, in run
File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 567, in _wrap SystemExit: 0

18.
Payment/Transfer Value (COM 2 Bermuda) window wait success1Passed: Job submitted. (Ref:0430008)finding transaction windowtrans_status:COMPLETED

Money Adjustment (COM 2 Bermuda) window wait successSave SuccessedSave Successedfinding transaction windowtrans_status:COMPLETED

19.
08/28/2023frmBTD (COM 2 Bermuda) window wait successBilling Date Reversal Succeededfinding transaction windowtrans_status:COMPLETED

20.
Coverage maintenance (COM 2 Bermuda) window wait success

Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 854, in test_25
_TC_LAS_CoverageMaintenance_01 File "system_view\LAS_view\las_functions_page.py", line 2197, in las_coverage_maintenance File "base_view\win_base_view.py", line 114, in
win_click_button File "pywinauto\controls\win32_controls.py", line 218, in click File "pywinauto\controls\hwndwrapper.py", line 749, in click File "pywinauto\base_wrapper.py", line 681,
in verify_actionable File "pywinauto\base_wrapper.py", line 692, in verify_enabled pywinauto.base_wrapper.ElementNotEnabled During handling of the above exception, another exception
occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File
"common\BeautifulReport\BeautifulReport.py", line 567, in _wrap SystemExit: 0

22.
Client Role Maintenance (COM 2 Bermuda) window wait successAre you sure want to delete this client?finding transaction windowtrans_status:COMPLETED

23.
frmPTDAdv (COM 2 Bermuda) window wait success 09/08/2047 Validation Error: Contract is currently used by other user

Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 909, in test_27
_TC_LAS_PaidToDateAdvance_01 File "system_view\LAS_view\las_functions_page.py", line 1502, in las_paid_to_date_advance Exception: job cannot submit successfully During handling
of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591, in run File
"unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 567, in _wrap SystemExit: 0

24.
Service Fee (COM 2 Bermuda) window wait success

Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 936, in test_28
_TC_LAS_DPMSServiceFee_Register_01 File "system_view\LAS_view\las_functions_page.py", line 2349, in las_dpms_service_fee_register File "base_view\win_base_view.py", line 280, in
win_date_time_picker_set_time File "pywinauto\controls\common_controls.py", line 3342, in set_time RuntimeError: Failed to set time in Date Time Picker During handling of the above
exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591, in run File "unittest\case.py",
line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 567, in _wrap SystemExit: 0

25.
Service Fee (COM 2 Bermuda) window wait success Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case
\las_test_case_all.py", line 963, in test_29_TC_LAS_DPMSServiceFee_termination_01 File "system_view\LAS_view\las_functions_page.py", line 2365, in las_dpms_service_fee_termination
File "base_view\win_base_view.py", line 114, in win_click_button File "pywinauto\controls\win32_controls.py", line 218, in click File "pywinauto\controls\hwndwrapper.py", line 749, in
click File "pywinauto\base_wrapper.py", line 681, in verify_actionable File "pywinauto\base_wrapper.py", line 692, in verify_enabled pywinauto.base_wrapper.ElementNotEnabled During
handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591, in run
File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in save_img File
"PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

26.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above
exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line
987, in test_30_TC_LAS_DirectCredit_01 File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py", line 226, in win_type_keys
File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move File "pywinauto
\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse cursor During
handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591, in run
File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in save_img File
"PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

27.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the
exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line
1013, in test_31_TC_LAS_DirectCreditHistory_01 File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py", line 226, in
win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move
File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse
cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591,
in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in
save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

28.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above
exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line
1039, in test_32_TC_LAS_AnnuityPaymentHistory_01 File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py", line 226, in
win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move
File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse
cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591,
in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in
save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

29.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above
exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line
1064, in test_33_TC_LAS_BounceCheque_01 File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py", line 226, in
win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move
File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse
cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591,
in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in
save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

30.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above
exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line
1089, in test_34_TC_LAS_BounceCheque_Reason_02 File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py", line 226, in
win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move
File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse
cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591,
in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in
save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

31.
(2, 'SetCursorPos', 'The system cannot find the file specified.') (2, 'SetCursorPos', 'The system cannot find the file specified.') (2, 'SetCursorPos', 'The system cannot find the file specified.')
(2, 'SetCursorPos', 'The system cannot find the file specified.') Traceback (most recent call last): File "pywinauto\application.py", line 250, in _resolve_control File "pywinauto\timings.py",
line 458, in wait_until_passes pywinauto.timings.TimeoutError During handling of the above exception, another exception occurred: Traceback (most recent call last): File "common
\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 1115, in test_35_TC_LAS_ClientBank_MandateApproval_01 File "system_view
\LAS_view\las_functions_page.py", line 1367, in las_client_bank_mandate_approval File "base_view\win_base_view.py", line 294, in win_date_time_picker_set_time_auto_id File
"pywinauto\controls\hwndwrapper.py", line 180, in _new_ File "pywinauto\base_wrapper.py", line 123, in _create_wrapper File "pywinauto\controls\hwndwrapper.py", line 194, in
__init__ File "pywinauto\application.py", line 379, in __getattr__ File "pywinauto\application.py", line 261, in _resolve_control File "pywinauto\timings.py", line 436, in
wait_until_passes File "pywinauto\application.py", line 203, in _get_ctrl File "pywinauto\findwindows.py", line 84, in find_element File "pywinauto\findwindows.py", line 305, in
find_elements File "pywinauto\findbestmatch.py", line 536, in find_best_control_matches pywinauto.findbestmatch.MatchError: Could not find 'Client Bank and Mandate Approval (COM 2
Bermuda)' in 'dict_keys(['WindowsForms10.Window.8.app.0.378734a0', 'WindowsForms10.Window.8.app.0.378734a1', 'Service Fee (COM 2 Bermuda)', 'Service Fee (COM 2 Bermuda)', 'WindowsForms10.Window.8.app.0.378734a3',
'WindowsForms10.Window.8.app.0.378734a4', 'WindowsForms10.Window.8.app.0.378734a2', 'Life Administration (COM 2 Bermuda) Main Menu (U401)', 'Life Administration (COM 2 Bermuda) Main
Menu (U401)']) During handling of the above exception, another exception occurred:
File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 1115, in test_35_TC_LAS_ClientBank_MandateApproval_01 File "system_view
\LAS_view\las_functions_page.py", line 1367, in las_client_bank_mandate_approval File "base_view\win_base_view.py", line 294, in win_date_time_picker_set_time_auto_id File
"pywinauto\controls\hwndwrapper.py", line 180, in _new_ File "pywinauto\base_wrapper.py", line 123, in _create_wrapper File "pywinauto\controls\hwndwrapper.py", line 194, in
__init__ File "pywinauto\application.py", line 379, in __getattr__ File "pywinauto\application.py", line 261, in _resolve_control File "pywinauto\timings.py", line 436, in
wait_until_passes File "pywinauto\application.py", line 203, in _get_ctrl File "pywinauto\findwindows.py", line 84, in find_element File "pywinauto\findwindows.py", line 305, in
find_elements File "pywinauto\findbestmatch.py", line 536, in find_best_control_matches pywinauto.findbestmatch.MatchError: Could not find 'Client Bank and Mandate Approval (COM 2
Bermuda)' in 'dict_keys(['WindowsForms10.Window.8.app.0.378734a0', 'WindowsForms10.Window.8.app.0.378734a1', 'Service Fee (COM 2 Bermuda)', 'Service Fee (COM 2 Bermuda)', 'WindowsForms10.Window.8.app.0.378734a3',
'WindowsForms10.Window.8.app.0.378734a4', 'WindowsForms10.Window.8.app.0.378734a2', 'Life Administration (COM 2 Bermuda) Main Menu (U401)', 'Life Administration (COM 2 Bermuda) Main
Menu (U401)']) During handling of the above exception, another exception occurred:
File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

32.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above
exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line
1141, in test_36_TC_LAS_ExtendGracePeriod_01 File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py", line 226, in
win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move
File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse
cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591,
in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in
save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

33.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above
exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line
1168, in test_37_TC_LAS_PolicyValueMaintenance_APL_01 File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py", line
226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in
move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving
mouse cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591,
in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in
save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

34.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the
exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line
1195, in test_38_TC_LAS_PolicyValueMaintenance_ChangeDividend_01 File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py",
line 226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244,
in move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse
cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591,
in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in
save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

35.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above
exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line
1222, in test_39_TC_LAS_PolicyValueMaintenance_ReDeposit_01 File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py",
line 226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244,
in move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for
moving mouse cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File
"unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case
\las_test_case_all.py", line 85, in save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

36.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above
exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line
1276, in test_41_TC_LAS_PolicyValueMaintenance_RPURegister_01 File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py",
line 226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244,
in move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse
cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591,
in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in
save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

37.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above
exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line
1303, in test_42_TC_LAS_PolicyValueMaintenance_ValueWithdraw_01 File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py",
line 226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244,
in move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse
cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 59, in testPartExecutor File "unittest\case.py", line 591,
in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in
save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed


38.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 1332, in test_56_TC_LAS_CoverageMaintenance_03_delete_rider File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py", line 226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

39.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 1360, in test_57_TC_LAS_IssueCheque_01 File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py", line 226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

40.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 1390, in test_58_TC_LAS_IssueCheque_ValueTransfer_01 File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py", line 226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

41.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 1423, in test_60_TC_LAS_Markin_Pending File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py", line 226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

42.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 1461, in test_61_TC_Withdraw_loan File "system_view\LAS_view\las_functions_page.py", line 2843, in las_value_withdraw File "base_view\win_base_view.py", line 226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

43.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 1540, in test_63_TC_Withdraw_Coupon File "system_view\LAS_view\las_functions_page.py", line 2843, in las_value_withdraw File "base_view\win_base_view.py", line 226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

44.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 1577, in test_64_TC_Withdraw_Dividend File "system_view\LAS_view\las_functions_page.py", line 2843, in las_value_withdraw File "base_view\win_base_view.py", line 226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

45.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 1608, in test_65_TC_Add_Role_Beneficiary File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py", line 226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

46.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 1694, in test_67_TC_Add_Loading_File File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py", line 226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

47.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 1727, in test_68_TC_VPO File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py", line 226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

48.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 1788, in test_70_TC_change_option_File File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py", line 226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

49.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 1820, in test_71_TC_coupon_payment File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py", line 226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

50.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 1850, in test_72_TC_currency_conversion File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py", line 226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed

51.
Traceback (most recent call last): File "pywinauto\mouse.py", line 59, in _set_cursor_pos pywintypes.error: (0, 'SetCursorPos', 'No error message is available') During handling of the above exception, another exception occurred: Traceback (most recent call last): File "common\BeautifulReport\BeautifulReport.py", line 554, in _wrap File "test_case\las_test_case_all.py", line 1884, in test_73_TC_confirm_address_change File "system_view\LAS_view\las_functions_page.py", line 133, in las_search_policy File "base_view\win_base_view.py", line 226, in win_type_keys File "pywinauto\base_wrapper.py", line 944, in type_keys File "pywinauto\controls\hwndwrapper.py", line 1309, in set_focus File "pywinauto\mouse.py", line 244, in move File "pywinauto\mouse.py", line 137, in _perform_click_input File "pywinauto\mouse.py", line 62, in _set_cursor_pos RuntimeError: There is no active desktop required for moving mouse cursor! During handling of the above exception, another exception occurred: Traceback (most recent call last): File "unittest\case.py", line 591, in run File "unittest\case.py", line 549, in _callTestMethod File "common\BeautifulReport\BeautifulReport.py", line 560, in _wrap File "test_case\las_test_case_all.py", line 85, in save_img File "PIL\ImageGrab.py", line 43, in grab OSError: screen grab failed
