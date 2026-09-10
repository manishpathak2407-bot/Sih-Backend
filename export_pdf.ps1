$pptPath = "C:\Users\manis\OneDrive\Desktop\Sih-Backend\ppt.pptx"
$pdfPath = "C:\Users\manis\OneDrive\Desktop\Sih-Backend\ppt.pdf"

Write-Host "Opening PowerPoint..."
$ppApp = New-Object -ComObject PowerPoint.Application
$ppApp.Visible = [Microsoft.Office.Core.MsoTriState]::msoTrue
try {
    $presentation = $ppApp.Presentations.Open($pptPath, [Microsoft.Office.Core.MsoTriState]::msoFalse, [Microsoft.Office.Core.MsoTriState]::msoFalse, [Microsoft.Office.Core.MsoTriState]::msoFalse)
    Write-Host "Saving as PDF..."
    $presentation.SaveAs($pdfPath, 32)
    $presentation.Close()
    Write-Host "PDF Exported Successfully: $pdfPath"
} catch {
    Write-Error $_.Exception.Message
} finally {
    $ppApp.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($ppApp) | Out-Null
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
}
