Attribute VB_Name = "DevDataValidator"
' ============================================================
' dev_data_validator.bas  -  DEV environment
' Validates incoming data rows before processing.
' Signed with the dev-signing certificate.
' ============================================================
Option Explicit

' Validate that a row from a named range has expected columns
Public Function ValidateDataRow(ws As Worksheet, rowNum As Long) As Boolean
    Dim requiredCols As Integer
    requiredCols = 6

    Dim col As Integer
    For col = 1 To requiredCols
        If IsEmpty(ws.Cells(rowNum, col).Value) Or Len(Trim(ws.Cells(rowNum, col).Value)) = 0 Then
            Debug.Print "Validation failed: row " & rowNum & " col " & col & " is empty"
            ValidateDataRow = False
            Exit Function
        End If
    Next col

    ' Check numeric columns (2, 4, 6)
    Dim numericCols As Variant
    numericCols = Array(2, 4, 6)
    Dim nc As Variant
    For Each nc In numericCols
        If Not IsNumeric(ws.Cells(rowNum, nc).Value) Then
            Debug.Print "Validation failed: row " & rowNum & " col " & nc & " is not numeric"
            ValidateDataRow = False
            Exit Function
        End If
    Next nc

    ValidateDataRow = True
End Function

' Validate all data rows in a sheet
Public Function ValidateSheet(ws As Worksheet, startRow As Long, endRow As Long) As Long
    Dim failCount As Long
    failCount = 0
    Dim r As Long
    For r = startRow To endRow
        If Not ValidateDataRow(ws, r) Then
            failCount = failCount + 1
        End If
    Next r
    ValidateSheet = failCount
End Function

' Entry point for manual testing in DEV
Public Sub RunDevValidation()
    Dim ws As Worksheet
    Set ws = ActiveSheet
    Dim lastRow As Long
    lastRow = ws.Cells(ws.Rows.Count, 1).End(xlUp).Row
    If lastRow < 2 Then
        MsgBox "No data to validate.", vbInformation
        Exit Sub
    End If
    Dim fails As Long
    fails = ValidateSheet(ws, 2, lastRow)
    If fails = 0 Then
        MsgBox "All " & (lastRow - 1) & " rows passed validation.", vbInformation, "DEV Validator"
    Else
        MsgBox fails & " row(s) failed validation. Check Immediate window.", vbExclamation, "DEV Validator"
    End If
End Sub
