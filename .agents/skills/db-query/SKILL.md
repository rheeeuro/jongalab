---
name: db-query
description: 프로젝트 MariaDB의 스키마나 데이터를 안전하게 읽기 전용으로 확인한다. 사용자가 DB 조회, 테이블 구조 확인, 저장 데이터 점검, 또는 Claude의 /db와 같은 작업을 요청할 때 사용한다.
---

# MariaDB 읽기 전용 조회

1. `docker ps --format '{{.Names}}'`로 MariaDB 컨테이너를 찾는다.
2. 접속 설정은 해당 서브프로젝트의 `core/config.py`를 통해 사용한다. `.env`를 읽거나 접속 값을 출력하지 않는다.
3. 기본적으로 `SELECT`, `SHOW`, `DESCRIBE`, `EXPLAIN`만 실행한다.
4. 조회 결과에는 필요한 열과 행만 포함하고 비밀값이나 개인정보를 노출하지 않는다.

주요 `jongalab` 테이블은 `content_analysis`, `daily_stock_report`, `sector_report`, `ticker_dictionary`, `source`, `daily_summary`, `telegram_user`다. 실제 스키마가 필요하면 `jongalab/sql/` 또는 repository 코드를 먼저 확인한다.

`INSERT`, `UPDATE`, `DELETE`, DDL은 실행 전에 사용자에게 명시적으로 확인받는다. 스키마 변경은 해당 `sql/` 디렉터리의 마이그레이션으로 관리한다.
