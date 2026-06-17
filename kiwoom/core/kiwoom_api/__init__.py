"""
키움증권 REST API 클라이언트 (데이터 조회 전용)
============================================================
도메인: api.kiwoom.com (운영) / mockapi.kiwoom.com (모의투자)
인증:   au10001 (OAuth2 토큰 발급)
헤더:   authorization, api-id, cont-yn, next-key

카테고리별 모듈을 Mixin 으로 분리하고 여기서 KiwoomRestAPI 로 조립한다.
공개 인터페이스(KiwoomConfig, KiwoomRestAPI)는 분리 전과 동일하다 —
`from core.kiwoom_api import KiwoomConfig, KiwoomRestAPI` 그대로 동작.

주문/계좌는 이 서버에서 다루지 않는다(데이터 조회 전용 가드레일). 주문/계좌 권한은
trading 도메인(core.kiwoom_order_client)이 키움 REST 를 직접 호출해 가진다.

[사용 TR 목록]
  au10001  접근토큰 발급          POST /oauth2/token
  au10002  접근토큰 폐기          POST /oauth2/token
  ka10001  주식기본정보요청        POST /api/dostk/stkinfo
  ka10100  종목정보조회            POST /api/dostk/stkinfo
  ka10002  주식거래원요청          POST /api/dostk/stkinfo
  ka10059  종목별투자자기관별요청  POST /api/dostk/stkinfo
  ka90004  종목별프로그램매매현황  POST /api/dostk/stkinfo
  ka90008  종목시간별프로그램매매  POST /api/dostk/mrktpr
  ka10032  거래대금상위요청        POST /api/dostk/rkinfo
  ka90009  외국인기관매매상위요청  POST /api/dostk/rkinfo
  ka10037  외국계창구매매상위요청  POST /api/dostk/rkinfo
  ka10035  외인연속순매매상위요청  POST /api/dostk/rkinfo
  ka90001  테마그룹별요청          POST /api/dostk/thme
  ka90002  테마구성종목요청        POST /api/dostk/thme
  ka10131  기관외국인연속매매현황  POST /api/dostk/frgnistt
  ka10008  주식외국인종목별매매동향 POST /api/dostk/frgnistt
  ka10009  주식기관요청            POST /api/dostk/frgnistt
  ka10080  주식분봉차트조회요청    POST /api/dostk/chart
  ka10081  주식일봉차트조회요청    POST /api/dostk/chart
"""
from core.kiwoom_api._base import KiwoomConfig, _BaseClient
from core.kiwoom_api.stock_info import StockInfoMixin
from core.kiwoom_api.market import MarketMixin
from core.kiwoom_api.rank import RankMixin
from core.kiwoom_api.theme import ThemeMixin
from core.kiwoom_api.frgn_inst import FrgnInstMixin
from core.kiwoom_api.chart import ChartMixin


class KiwoomRestAPI(
    StockInfoMixin,
    MarketMixin,
    RankMixin,
    ThemeMixin,
    FrgnInstMixin,
    ChartMixin,
    _BaseClient,
):
    """키움증권 REST API 래퍼 — 카테고리 Mixin 조립 (데이터 조회 전용)."""


__all__ = ["KiwoomConfig", "KiwoomRestAPI"]
