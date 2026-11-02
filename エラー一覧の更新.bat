@echo off
setlocal
rem docs\ERRORS.md のエラー名の表を、src\ と comken の例外から作り直す。
rem エラーを足したり docstring を直したりしたら実行する。
rem .py の名前を英数字にしているのは、日本語以外のコードページの Windows でも探せるようにするため。
rem comken の場所は書かない（認証情報の登録.bat と同じく、comken を読み込める PC で叩く前提）。
pushd "%~dp0" || (echo [エラー] フォルダ未到達: %~dp0 & exit /b 1)
where python >nul 2>&1 || (echo [エラー] Python 未インストール & popd & exit /b 1)
python update_errors.py
set "EXIT_CODE=%ERRORLEVEL%"
popd
if not "%EXIT_CODE%"=="0" echo [失敗] 終了コード %EXIT_CODE%
endlocal & exit /b %EXIT_CODE%
