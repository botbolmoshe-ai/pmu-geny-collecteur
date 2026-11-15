"""Réessais bornés des lectures idempotentes, jamais des append Sheets."""
import time


def get_lecture(session,url,**kwargs):
    for attempt in range(4):
        response=session.get(url,**kwargs)
        if response.status_code not in (429,500,502,503,504) or attempt==3:return response
        delay=min(15*2**attempt,60) if response.status_code==429 else 2**attempt
        try:delay=max(delay,float(getattr(response,'headers',{}).get('Retry-After',0)))
        except (TypeError,ValueError):pass
        # Ne pas réessayer avant un long délai demandé : la file reprendra.
        if delay>60:return response
        time.sleep(delay)
