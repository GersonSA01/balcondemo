Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Iniciando servidor de desarrollo Vite" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Set-Location frontend
Write-Host "Directorio actual: $(Get-Location)" -ForegroundColor Yellow
Write-Host ""
Write-Host "Ejecutando: npm run dev" -ForegroundColor Green
Write-Host ""
Write-Host "IMPORTANTE: Deja esta ventana abierta mientras trabajas" -ForegroundColor Red
Write-Host ""
npm run dev








