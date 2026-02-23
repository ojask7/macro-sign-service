Attribute VB_Name = "DevReportGenerator"
' ============================================================
' dev_report_generator.vba  -  DEV environment
' Generates a weekly summary report sheet from raw data.
' Signed with the dev-signing certificate.
' ============================================================
Option Explicit

Public Sub GenerateWeeklyReport()
    Dim ws As Worksheet
    Dim rawWs As Worksheet
    Dim reportDate As String
    reportDate = Format(Date, "YYYY-MM-DD")

    ' Get or create sheets
    On Error Resume Next
    Set rawWs = ThisWorkbook.Sheets("RawData")
    Set ws = ThisWorkbook.Sheets("WeeklyReport")
    If ws Is Nothing Then
        Set ws = ThisWorkbook.Sheets.Add(After:=ThisWorkbook.Sheets(ThisWorkbook.Sheets.Count))
        ws.Name = "WeeklyReport"
    End If
    On Error GoTo 0

    ws.Cells.ClearContents

    ' Title row
    ws.Range("A1").Value = "Weekly Macro Signing Report"
    ws.Range("A2").Value = "Environment: DEV"
    ws.Range("A3").Value = "Generated: " & reportDate

    ' Column headers
    ws.Range("A5").Value = "Department"
    ws.Range("B5").Value = "Macros Signed"
    ws.Range("C5").Value = "Failures"
    ws.Range("D5").Value = "Success Rate"
    ws.Range("E5").Value = "Avg Sign Time (ms)"

    ' Sample dev data
    Dim rows(1 To 5, 1 To 5) As Variant
    rows(1, 1) = "Engineering":   rows(1, 2) = 42:  rows(1, 3) = 0: rows(1, 5) = 230
    rows(2, 1) = "Finance":       rows(2, 2) = 18:  rows(2, 3) = 1: rows(2, 5) = 310
    rows(3, 1) = "Data Ops":      rows(3, 2) = 35:  rows(3, 3) = 0: rows(3, 5) = 190
    rows(4, 1) = "HR":            rows(4, 2) = 8:   rows(4, 3) = 0: rows(4, 5) = 275
    rows(5, 1) = "Operations":    rows(5, 2) = 21:  rows(5, 3) = 2: rows(5, 5) = 340

    Dim i As Integer
    For i = 1 To 5
        ws.Cells(5 + i, 1).Value = rows(i, 1)
        ws.Cells(5 + i, 2).Value = rows(i, 2)
        ws.Cells(5 + i, 3).Value = rows(i, 3)
        If rows(i, 2) > 0 Then
            ws.Cells(5 + i, 4).Value = Format((rows(i, 2) - rows(i, 3)) / rows(i, 2), "0.0%")
        End If
        ws.Cells(5 + i, 5).Value = rows(i, 5)
    Next i

    MsgBox "DEV weekly report generated for " & reportDate, vbInformation, "DevReportGenerator"
End Sub
