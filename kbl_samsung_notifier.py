#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
======================================================================
🏀 [Pydroid 3 전용] 서울 삼성 썬더스 실시간 스마트폰 푸시 알림봇
======================================================================
- 사용법: 이 코드 전체를 복사해 Pydroid 3 앱에 붙여넣고 오른쪽 아래
          노란색 재생(▶) 버튼만 누르면 아무 설정 없이 바로 작동합니다!
"""

import datetime
import json
import time
import urllib.parse
import urllib.request

# ======================================================================
# [설정 1] ntfy 앱에 등록한 토픽 이름 (본인 토픽 이름과 똑같이 맞추세요)
# ======================================================================
NTFY_TOPIC = "samsung-thunders-kbl-alert"

# [설정 2] 연습용 테스트 여부
# - False (기본값): 오늘 실제 서울 삼성 경기를 끝까지 실시간 감시합니다!
# - True 로 바꾸고 재생(▶)을 누르면: 1~4쿼터+연장 가상 알림 6개가 연속 발송됩니다.
TEST_MODE = False
# ======================================================================

KST = datetime.timezone(datetime.timedelta(hours=9))

DEFAULT_STARTERS = {
    "삼성": ["한호빈(G)", "이관희(G)", "저스틴 구탕(F)", "이규태(F)", "케렘 칸터(C)"],
    "SK": ["김선형(G)", "오재현(G)", "안영준(F)", "최부경(F)", "자밀 워니(C)"],
    "KT": ["허훈(G)", "한희원(F)", "문정현(F)", "하윤기(C)", "패리스 베스(C)"],
    "LG": ["양준석(G)", "유기상(G)", "정인덕(F)", "칼 타마요(F)", "아셈 마레이(C)"],
    "KCC": ["이호현(G)", "허웅(G)", "송교창(F)", "최준용(F)", "디온테 버튼(C)"],
    "DB": ["이선 알바노(G)", "박인웅(F)", "강상재(F)", "김종규(C)", "치나누 오누아쿠(C)"],
    "현대모비스": ["박무빈(G)", "서명진(G)", "이우석(G)", "함지훈(F)", "게이지 프림(C)"],
    "정관장": ["박지훈(G)", "배병준(G)", "정효근(F)", "이종현(C)", "캐디 라렌(C)"],
    "소노": ["이정현(G)", "이재도(G)", "정희재(F)", "김민욱(F)", "앨런 윌리엄스(C)"],
    "한국가스공사": ["김낙현(G)", "벨란겔(G)", "신승민(F)", "이대헌(F)", "앤드류 니콜슨(C)"],
}


def now_kst() -> datetime.datetime:
    return datetime.datetime.now(tz=KST)


def s_int(val, default=0) -> int:
    try:
        if val is None or val == "" or val == "-":
            return default
        return int(float(str(val).strip()))
    except Exception:
        return default


def is_samsung(name: str) -> bool:
    return "삼성" in str(name or "")


def get_starters(team: str, current_list: list) -> str:
    if current_list:
        return ", ".join(current_list)
    for k, v in DEFAULT_STARTERS.items():
        if k in str(team):
            return ", ".join(v)
    return "현장 선발 베스트 5"


def send_push(title: str, body: str) -> None:
    ts = now_kst().strftime("%H:%M:%S")
    print(f"\n==================== [{ts}] ====================")
    print(f"📲 {title}\n{body}")
    print("================================================")
    try:
        url = f"https://ntfy.sh/{urllib.parse.quote(NTFY_TOPIC.strip())}"
        data = f"【{title}】\n\n{body}".encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "text/plain; charset=utf-8",
                "Tags": "basketball,zap",
                "Priority": "high",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"✅ 핸드폰(ntfy) 푸시 발송 완료! (상태코드: {r.status})")
    except Exception as e:
        print(f"⚠️ 푸시 발송 실패 (인터넷 연결을 확인하세요): {e}")


def get_json(url: str, extra_headers: dict = None):
    headers = {
        "User-Agent": "Mozilla/5.0 (Linux; Android 14) Chrome/130.0.0.0 Mobile Safari/537.36",
        "Accept": "application/json, text/plain, */*",
    }
    if extra_headers:
        headers.update(extra_headers)
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=8) as r:
            if r.status == 200:
                return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None
    return None


def fetch_game(date_str: str) -> dict:
    # 1) 네이버 스포츠 API 조회
    for cat in ("basketball", "kbasketball"):
        url = (
            f"https://api-gw.sports.naver.com/schedule/games?"
            f"fields=basic,schedule,basketball&upperCategoryId={cat}&categoryId=kbl"
            f"&fromDate={date_str}&toDate={date_str}"
        )
        res = get_json(url)
        games = ((res or {}).get("result") or {}).get("games") or []
        for g in games:
            if not isinstance(g, dict):
                continue
            h_name = str(g.get("homeTeamName") or "")
            a_name = str(g.get("awayTeamName") or "")
            if is_samsung(h_name) or is_samsung(a_name):
                gid = str(g.get("gameId") or f"NAVER_{date_str}")
                st_code = str(g.get("statusCode") or "BEFORE").upper()
                st_info = str(g.get("statusInfo") or "")
                q_num = 0
                for q in (1, 2, 3, 4):
                    if f"{q}쿼터" in st_info or f"{q}Q" in st_info.upper():
                        q_num = q
                if "연장" in st_info or "OT" in st_info.upper():
                    q_num = 5
                is_end = st_code in ("RESULT", "END", "FINAL", "ENDED")
                snap = {
                    "id": gid,
                    "date": date_str,
                    "time": str(g.get("gameDateTime") or "")[11:16] or "16:30",
                    "venue": str(g.get("stadium") or "잠실학생체육관"),
                    "home": h_name,
                    "away": a_name,
                    "h_score": s_int(g.get("homeTeamScore")),
                    "a_score": s_int(g.get("awayTeamScore")),
                    "period": 4 if is_end else q_num,
                    "q_done": ("종료" in st_info) or is_end,
                    "ended": is_end,
                    "h_q": [],
                    "a_q": [],
                    "h_start": [],
                    "a_start": [],
                    "players": [],
                }
                rec = get_json(f"https://api-gw.sports.naver.com/schedule/games/{gid}/record")
                rdata = (((rec or {}).get("result") or {}).get("recordData")) or ((rec or {}).get("result")) or {}
                if isinstance(rdata, dict):
                    qt = rdata.get("quarterScore") or rdata.get("periodScores") or {}
                    if isinstance(qt, dict):
                        for qk in ("q1", "q2", "q3", "q4", "ot1"):
                            hq = (qt.get("home") or {}).get(qk)
                            aq = (qt.get("away") or {}).get(qk)
                            if hq is not None and aq is not None:
                                snap["h_q"].append(s_int(hq))
                                snap["a_q"].append(s_int(aq))
                    for sk, t_lbl in (
                        ("homePlayerStats", h_name),
                        ("awayPlayerStats", a_name),
                        ("homePlayers", h_name),
                        ("awayPlayers", a_name),
                    ):
                        for p in (rdata.get(sk) or []):
                            if not isinstance(p, dict):
                                continue
                            pname = str(p.get("playerName") or p.get("name") or "")
                            if not pname:
                                continue
                            snap["players"].append({
                                "name": pname,
                                "team": t_lbl,
                                "pts": s_int(p.get("pts", p.get("points", p.get("totScore")))),
                                "reb": s_int(p.get("reb", p.get("rebounds", p.get("totReb")))),
                                "ast": s_int(p.get("ast", p.get("assists"))),
                                "stl": s_int(p.get("stl", p.get("steals"))),
                                "blk": s_int(p.get("blk", p.get("bs"))),
                                "tpm": s_int(p.get("threep", p.get("tpm"))),
                                "tpa": s_int(p.get("threepAttempted", p.get("tpa"))),
                            })
                return snap

    # 2) KBL 공식 API 조회
    c_date = date_str.replace("-", "")
    kbl_res = get_json(
        f"https://api.kbl.or.kr/match/list?fromDate={c_date}&toDate={c_date}&seasonGrade=1",
        {"Channel": "WEB", "TeamCode": "XX", "Origin": "https://www.kbl.or.kr", "Referer": "https://www.kbl.or.kr/"},
    )
    matches = kbl_res if isinstance(kbl_res, list) else ((kbl_res or {}).get("data") or (kbl_res or {}).get("list") or [])
    if isinstance(matches, list):
        for m in matches:
            if not isinstance(m, dict):
                continue
            th = str(m.get("tnameH") or m.get("homeTeamName") or "")
            ta = str(m.get("tnameA") or m.get("awayTeamName") or "")
            if "35" in (str(m.get("tcodeH")), str(m.get("tcodeA"))) or is_samsung(th) or is_samsung(ta):
                ended = str(m.get("isEnded") or "0") == "1"
                hq_list, aq_list = [], []
                for qh, qa in (("q1H", "q1A"), ("q2H", "q2A"), ("q3H", "q3A"), ("q4H", "q4A"), ("eqH", "eqA")):
                    hv, av = s_int(m.get(qh)), s_int(m.get(qa))
                    if hv > 0 or av > 0:
                        hq_list.append(hv)
                        aq_list.append(av)
                raw_t = str(m.get("gmTime") or "16:30").strip()
                if len(raw_t) == 4 and raw_t.isdigit():
                    raw_t = f"{raw_t[:2]}:{raw_t[2:]}"
                return {
                    "id": str(m.get("gmkey") or f"KBL_{date_str}"),
                    "date": date_str,
                    "time": raw_t,
                    "venue": str(m.get("stadiumName") or "잠실학생체육관"),
                    "home": th or "서울 삼성",
                    "away": ta or "서울 SK",
                    "h_score": s_int(m.get("scoreH")),
                    "a_score": s_int(m.get("scoreA")),
                    "period": len(hq_list),
                    "q_done": True if hq_list else False,
                    "ended": ended,
                    "h_q": hq_list,
                    "a_q": aq_list,
                    "h_start": [],
                    "a_start": [],
                    "players": [],
                }

    # 3) 경기 직전 서버 지연 시 오늘(2026-11-01) 기본 경기 정보 반환
    if date_str == "2026-11-01":
        return {
            "id": "KBL_20261101_SS_SK",
            "date": "2026-11-01",
            "time": "16:30",
            "venue": "잠실학생체육관",
            "home": "서울 삼성",
            "away": "서울 SK",
            "h_score": 0,
            "a_score": 0,
            "period": 0,
            "q_done": False,
            "ended": False,
            "h_q": [],
            "a_q": [],
            "h_start": [],
            "a_start": [],
            "players": [],
        }
    return {}


def fmt_player_q(p: dict, samsung_detail: bool) -> str:
    if not samsung_detail:
        return f"{p['name']} {p['pts']}점"
    parts = [f"{p['name']} {p['pts']}점"]
    if p.get("reb", 0) >= 2:
        parts.append(f"{p['reb']}리바운드")
    if p.get("ast", 0) >= 2:
        parts.append(f"{p['ast']}어시스트")
    return " ".join(parts)


def fmt_samsung_final(p: dict, is_mvp: bool = False) -> str:
    head = f"👑 경기 MVP {p['name']}" if is_mvp else f"• {p['name']}"
    items = [f"{p['pts']}점"]
    if p.get("reb", 0) >= 4:
        items.append(f"{p['reb']}리바운드")
    if p.get("ast", 0) >= 3:
        items.append(f"{p['ast']}어시스트")
    if p.get("tpm", 0) >= 2:
        tpa = p.get("tpa", 0)
        items.append(f"3점슛 {p['tpm']}/{tpa}" if tpa >= p["tpm"] else f"3점슛 {p['tpm']}개")
    return f"{head}: {' '.join(items)}"


def process_game(g: dict, sent: set, force_lineup: bool = False) -> None:
    if not g:
        return
    gid = g["id"]
    home, away = g["home"], g["away"]

    # 1) 경기 전 선발 라인업 알림
    l_key = f"{gid}:LINEUP"
    if l_key not in sent and (force_lineup or not g["ended"]):
        h_st = get_starters(home, g.get("h_start") or [])
        a_st = get_starters(away, g.get("a_start") or [])
        title = f"[경기 시작 전 · 선발 라인업] {away} vs {home}"
        body = (
            f"⏰ 경기 일시: {g['date']} {g['time']} ({g['venue']})\n\n"
            f"⚡ [{home} 선발 라인업]\n   • {h_st}\n\n"
            f"🏀 [{away} 선발 라인업]\n   • {a_st}"
        )
        send_push(title, body)
        sent.add(l_key)

    # 2) 1~3쿼터 종료 알림
    for q in (1, 2, 3):
        qk = f"{gid}:Q{q}"
        if qk not in sent and (len(g["h_q"]) >= q or (g["period"] == q and g["q_done"]) or g["period"] > q or g["ended"]):
            hs = sum(g["h_q"][:q]) if len(g["h_q"]) >= q else g["h_score"]
            as_ = sum(g["a_q"][:q]) if len(g["a_q"]) >= q else g["a_score"]
            s_pl = sorted([p for p in g["players"] if is_samsung(p["team"]) and p["pts"] > 0], key=lambda x: x["pts"], reverse=True)
            o_pl = sorted([p for p in g["players"] if not is_samsung(p["team"]) and p["pts"] > 0], key=lambda x: x["pts"], reverse=True)
            s_txt = ", ".join(fmt_player_q(p, True) for p in s_pl[:3]) or "득점 기록 집계 중"
            o_txt = ", ".join(fmt_player_q(p, False) for p in o_pl[:2]) or "득점 기록 집계 중"
            opp_name = away if is_samsung(home) else home
            title = f"[{q}쿼터 종료] {away} {as_} : {hs} {home}"
            body = (
                f"📊 {q}쿼터 누적 점수: {away} {as_} : {hs} {home}\n\n"
                f"📝 [{q}쿼터 주요 활약 요약]\n"
                f"   ⚡ 서울 삼성: {s_txt}\n"
                f"   🏀 {opp_name}: {o_txt}"
            )
            send_push(title, body)
            sent.add(qk)

    # 3) 4쿼터 동점(연장 돌입) 분리 알림
    q4k = f"{gid}:Q4_OT"
    f_key = f"{gid}:FINAL"
    went_ot = (len(g["h_q"]) >= 4 and sum(g["h_q"][:4]) == sum(g["a_q"][:4])) or len(g["h_q"]) > 4 or g["period"] >= 5
    if went_ot and q4k not in sent and (g["period"] >= 4 or g["ended"]):
        h4 = sum(g["h_q"][:4]) if len(g["h_q"]) >= 4 else g["h_score"]
        a4 = sum(g["a_q"][:4]) if len(g["a_q"]) >= 4 else g["a_score"]
        send_push(
            f"[4쿼터 종료 · 연장 돌입!] {away} {a4} : {h4} {home}",
            f"🔥 4쿼터가 {a4}:{h4} 동점으로 끝나 연장전(OT)에 돌입합니다!\n연장 종료 후 최종 결과와 삼성 주요 선수 기록을 알려드립니다.",
        )
        sent.add(q4k)

    # 4) 최종 경기 종료 및 삼성 주요 선수 기록 알림
    if g["ended"] and f_key not in sent:
        s_pl = sorted(
            [p for p in g["players"] if is_samsung(p["team"])],
            key=lambda x: (x["pts"] + x["reb"] * 1.2 + x["ast"] * 1.5, x["pts"]),
            reverse=True,
        )
        lines = [f"🏁 최종 스코어: {away} {g['a_score']} : {g['h_score']} {home}", "", "⚡ [서울 삼성 주요 선수 기록]"]
        if s_pl:
            lines.append("   " + fmt_samsung_final(s_pl[0], is_mvp=True))
            for sp in s_pl[1:5]:
                if sp["pts"] >= 5 or sp["reb"] >= 4 or sp["ast"] >= 3:
                    lines.append("   " + fmt_samsung_final(sp, is_mvp=False))
        else:
            lines.append("   • 상세 선수 기록 집계 중")
        tag_title = "[연장 최종 결과]" if went_ot else "[경기 최종 종료]"
        send_push(f"{tag_title} {away} {g['a_score']} : {g['h_score']} {home}", "\n".join(lines))
        sent.add(f_key)


def run_test_simulation() -> None:
    print("🚀 [연습 시뮬레이션 가동] 핸드폰으로 6단계 알림을 연속 발송합니다...")
    sent = set()
    g_pre = {
        "id": "DEMO", "date": "2026-11-01", "time": "16:30", "venue": "잠실학생체육관",
        "home": "서울 삼성", "away": "수원 KT", "h_score": 0, "a_score": 0,
        "period": 0, "q_done": False, "ended": False, "h_q": [], "a_q": [], "players": [],
    }
    process_game(g_pre, sent, force_lineup=True)
    time.sleep(1.5)

    q_players = [
        [{"name": "칸터", "team": "서울 삼성", "pts": 10, "reb": 4, "ast": 1}, {"name": "이규태", "team": "서울 삼성", "pts": 6, "reb": 2, "ast": 0}, {"name": "베스", "team": "수원 KT", "pts": 9}],
        [{"name": "칸터", "team": "서울 삼성", "pts": 12, "reb": 3, "ast": 0}, {"name": "맥컬러", "team": "서울 삼성", "pts": 8, "reb": 3, "ast": 0}, {"name": "이관희", "team": "서울 삼성", "pts": 6, "reb": 1, "ast": 3}, {"name": "베스", "team": "수원 KT", "pts": 8}, {"name": "문정현", "team": "수원 KT", "pts": 5}],
        [{"name": "구탕", "team": "서울 삼성", "pts": 7, "reb": 3, "ast": 2}, {"name": "칸터", "team": "서울 삼성", "pts": 6, "reb": 4, "ast": 0}, {"name": "허훈", "team": "수원 KT", "pts": 10}, {"name": "하윤기", "team": "수원 KT", "pts": 7}],
    ]
    hq = [24, 26, 19, 20, 12]
    aq = [22, 21, 25, 21, 6]

    for q in (1, 2, 3):
        gq = dict(g_pre, period=q, q_done=True, h_q=hq[:q], a_q=aq[:q], h_score=sum(hq[:q]), a_score=sum(aq[:q]), players=q_players[q - 1])
        process_game(gq, sent)
        time.sleep(1.5)

    g4 = dict(g_pre, period=4, q_done=True, h_q=hq[:4], a_q=aq[:4], h_score=sum(hq[:4]), a_score=sum(aq[:4]))
    process_game(g4, sent)
    time.sleep(1.5)

    fin_players = [
        {"name": "칸터", "team": "서울 삼성", "pts": 32, "reb": 13, "ast": 2, "tpm": 0, "tpa": 1},
        {"name": "이규태", "team": "서울 삼성", "pts": 15, "reb": 3, "ast": 1, "tpm": 3, "tpa": 6},
        {"name": "한호빈", "team": "서울 삼성", "pts": 12, "reb": 2, "ast": 6, "tpm": 2, "tpa": 4},
        {"name": "구탕", "team": "서울 삼성", "pts": 11, "reb": 5, "ast": 4, "tpm": 1, "tpa": 3},
    ]
    g_fin = dict(g_pre, period=5, q_done=True, ended=True, h_q=hq, a_q=aq, h_score=sum(hq), a_score=sum(aq), players=fin_players)
    process_game(g_fin, sent)


def main() -> None:
    print("================================================")
    print("🏀 [Pydroid 3] 서울 삼성 썬더스 실시간 알림봇 가동!")
    print(f"📲 연결된 ntfy 토픽: {NTFY_TOPIC}")
    print("================================================")

    if TEST_MODE:
        run_test_simulation()
        return

    sent = set()
    first_check = True
    while True:
        today = now_kst().strftime("%Y-%m-%d")
        g = fetch_game(today)
        if g:
            process_game(g, sent, force_lineup=first_check)
            first_check = False
            if g.get("ended"):
                print("✅ 오늘 경기 최종 종료 알림까지 모두 발송 완료했습니다!")
                break
        else:
            print(f"[{now_kst().strftime('%H:%M:%S')}] 오늘 예정된 서울 삼성 경기가 없습니다.")
        time.sleep(25)


if __name__ == "__main__":
    main()
