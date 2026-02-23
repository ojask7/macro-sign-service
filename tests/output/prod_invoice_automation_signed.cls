VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
END
Attribute VB_Name = "ProdInvoiceAutomation"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
' ============================================================
' prod_invoice_automation.cls  -  PRODUCTION environment
' Automates invoice generation and email dispatch.
' Signed with the prod-signing certificate.
' ============================================================
Option Explicit

Private mWorkbook   As Workbook
Private mSmtpServer As String
Private mSenderAddr As String

' ─── Initialisation ──────────────────────────────────────────────────────────
Public Sub Init(wb As Workbook, smtpServer As String, senderAddr As String)
    Set mWorkbook = wb
    mSmtpServer  = smtpServer
    mSenderAddr  = senderAddr
End Sub

' ─── Public API ──────────────────────────────────────────────────────────────
Public Function GenerateInvoice(customerID As String, amount As Double, dueDate As Date) As String
    Dim invoiceNum As String
    invoiceNum = "INV-" & Format(Now, "YYYYMMDD-HHNNSS") & "-" & Left(customerID, 4)

    Dim ws As Worksheet
    Set ws = mWorkbook.Sheets.Add
    ws.Name = invoiceNum

    ws.Range("A1").Value = "INVOICE"
    ws.Range("B1").Value = invoiceNum
    ws.Range("A3").Value = "Customer ID:"
    ws.Range("B3").Value = customerID
    ws.Range("A4").Value = "Amount Due:"
    ws.Range("B4").Value = amount
    ws.Range("B4").NumberFormat = "$#,##0.00"
    ws.Range("A5").Value = "Due Date:"
    ws.Range("B5").Value = dueDate
    ws.Range("B5").NumberFormat = "YYYY-MM-DD"
    ws.Range("A7").Value = "Status:"
    ws.Range("B7").Value = "PENDING"

    GenerateInvoice = invoiceNum
End Function

Public Sub SendInvoiceEmail(invoiceNum As String, recipientEmail As String)
    ' Production email dispatch via CDO
    Debug.Print "Sending invoice " & invoiceNum & " to " & recipientEmail & " via " & mSmtpServer
    ' CDO send logic would go here in production
End Sub

Public Function GetPendingInvoices() As Collection
    Dim result As New Collection
    Dim ws As Worksheet
    For Each ws In mWorkbook.Sheets
        If Left(ws.Name, 4) = "INV-" Then
            If ws.Range("B7").Value = "PENDING" Then
                result.Add ws.Name
            End If
        End If
    Next ws
    Set GetPendingInvoices = result
End Function

Public Sub MarkAsPaid(invoiceNum As String, paymentDate As Date)
    Dim ws As Worksheet
    On Error Resume Next
    Set ws = mWorkbook.Sheets(invoiceNum)
    On Error GoTo 0
    If ws Is Nothing Then Exit Sub
    ws.Range("B7").Value = "PAID"
    ws.Range("A8").Value = "Payment Date:"
    ws.Range("B8").Value = paymentDate
    ws.Range("B8").NumberFormat = "YYYY-MM-DD"
End Sub
