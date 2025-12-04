import pyodbc

# 연결에 필요한 정보들을 변수로 명확하게 정의합니다.
driver = "{ODBC Driver 17 for SQL Server}"
server = "192.68.10.249"
port = "1433"
database = "ChatBot"
username = "soosan_chatbot_svc"
password = "chatBot2025!"

# pyodbc를 위한 연결 문자열 생성
# SSMS에서 성공했으므로, 암호화 옵션(Encrypt)은 우선 'no'로 시도합니다.
conn_str = f"DRIVER={driver};SERVER={server},{port};DATABASE={database};UID={username};PWD={password};Encrypt=no;TrustServerCertificate=yes;"

print("pyodbc를 통해 직접 연결을 시도합니다...")
print(f"사용할 연결 문자열: {conn_str}")

try:
    # 직접 연결 시도
    cnxn = pyodbc.connect(conn_str)
    print("\n✅ 연결 성공! Connection Successful!")
    cnxn.close()

except pyodbc.Error as ex:
    # 실패 시, pyodbc가 반환하는 가장 상세한 오류 메시지를 출력합니다.
    print("\n❌ 연결 실패! Connection Failed.")
    print("-------------------------------------")
    print(f"Error Details: {ex}")
    print(f"SQLSTATE: {ex.args[0]}")
    print("-------------------------------------")
