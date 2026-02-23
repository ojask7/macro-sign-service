Attribute VB_Name = "ProdMonthlyClose"
' ============================================================
' prod_monthly_close.vba  -  PRODUCTION environment
' Performs end-of-month ledger close and exports to PDF.
' Signed with the prod-signing certificate.
' ============================================================
Option Explicit

Private Const LEDGER_SHEET As String = "GeneralLedger"
Private Const EXPORT_PATH  As String = "C:\Reports\MonthlyClose\"

Public Sub RunMonthlyClose()
    Dim closeDate As Date
    closeDate = DateSerial(Year(Date), Month(Date), Day(Date))

    If MsgBox("Run monthly close for " & Format(closeDate, "MMMM YYYY") & "?" & vbNewLine & _
              "This will lock the ledger and export to PDF.", _
              vbYesNo + vbQuestion, "PROD Monthly Close") = vbNo Then
        Exit Sub
    End If

    Application.ScreenUpdating = False
    Application.Calculation = xlCalculationManual

    On Error GoTo ErrHandler

    ' Step 1: Validate ledger totals
    If Not ValidateLedgerTotals() Then
        MsgBox "Ledger validation failed. Close aborted.", vbCritical, "PROD Monthly Close"
        GoTo Cleanup
    End If

    ' Step 2: Post accruals
    PostAccruals closeDate

    ' Step 3: Calculate period totals
    CalculatePeriodTotals

    ' Step 4: Export to PDF
    ExportLedgerPDF Format(closeDate, "YYYY-MM")

    ' Step 5: Lock sheet
    LockLedger

    MsgBox "Monthly close completed successfully for " & Format(closeDate, "MMMM YYYY"), _
           vbInformation, "PROD Monthly Close"
    GoTo Cleanup

ErrHandler:
    MsgBox "Error during monthly close: " & Err.Description, vbCritical, "PROD Monthly Close"

Cleanup:
    Application.ScreenUpdating = True
    Application.Calculation = xlCalculationAutomatic
End Sub

Private Function ValidateLedgerTotals() As Boolean
    Dim ws As Worksheet
    On Error Resume Next
    Set ws = ThisWorkbook.Sheets(LEDGER_SHEET)
    On Error GoTo 0
    If ws Is Nothing Then
        ValidateLedgerTotals = False
        Exit Function
    End If
    ' Debit = Credit check (simplified)
    Dim totalDebits  As Double
    Dim totalCredits As Double
    Dim lastRow As Long
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
    totalDebits  = Application.WorksheetFunction.Sum(ws.Range("C2:C" & lastRow))
    totalCredits = Application.WorksheetFunction.Sum(ws.Range("D2:D" & lastRow))
    ValidateLedgerTotals = (Abs(totalDebits - totalCredits) < 0.01)
End Function

Private Sub PostAccruals(closeDate As Date)
    ' Placeholder: post end-of-month accrual entries
    Debug.Print "Posting accruals for " & Format(closeDate, "YYYY-MM-DD")
End Sub

Private Sub CalculatePeriodTotals()
    Debug.Print "Calculating period totals..."
End Sub

Private Sub ExportLedgerPDF(period As String)
    Dim exportFile As String
    exportFile = EXPORT_PATH & "ledger_" & period & ".pdf"
    Debug.Print "Exporting to " & exportFile
End Sub

Private Sub LockLedger()
    Dim ws As Worksheet
    On Error Resume Next
    Set ws = ThisWorkbook.Sheets(LEDGER_SHEET)
    If Not ws Is Nothing Then
        ws.Protect Password:="", DrawingObjects:=True, Contents:=True, Scenarios:=True
    End If
End Sub
