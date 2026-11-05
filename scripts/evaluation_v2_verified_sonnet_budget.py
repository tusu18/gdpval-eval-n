"""New-request-only Sonnet5.5 image reservation; never edit old ledger rows."""
import math
from extend_evaluation_v2_models import verified_small_image
from run_evaluation_v2 import ROOT, canonical, digest

EVIDENCE = ROOT/'docs/evaluation_v2/continuation-sonnet-image-budget-evidence.json'
MODEL = 'anthropic/claude-sonnet-5.5'


def sonnet_reservation_detail(client, body):
    if body['model'] != MODEL:
        raise ValueError('This bound is verified only for exact Sonnet5.5')
    pricing=client.models[body['model']]['pricing']
    verified=fallback=image_tokens=0
    def clean(value):
        nonlocal verified,fallback,image_tokens
        if isinstance(value,dict):
            if value.get('type') in ('input_image','image_url'):
                if verified_small_image(value):image_tokens+=8192;verified+=1
                else:image_tokens+=40000;fallback+=1
                return {'image_omitted_from_text_token_bound':True}
            return {k:clean(v) for k,v in value.items()}
        if isinstance(value,list):return [clean(v) for v in value]
        return value
    text_body=clean(body)
    tokens=len(canonical(text_body).encode())+2048+image_tokens
    ip=max(float(pricing.get(k,0)) for k in ('prompt','input_cache_write','input_cache_write_1h'))
    op=float(pricing['completion'])
    for tier in pricing.get('overrides',[]):
        if tokens>=tier.get('min_prompt_tokens',math.inf):
            ip=max(ip,float(tier.get('prompt',0)),float(tier.get('input_cache_write',0)))
            op=max(op,float(tier.get('completion',0)))
    maximum=body.get('max_output_tokens',body.get('max_tokens'))
    amount=round((tokens*ip+maximum*op+(verified+fallback)*float(pricing.get('image',0)))*1.05+.002,8)
    return {'reserved_usd':amount,'input_token_bound':tokens,'verified_images':verified,'fallback_images':fallback,
            'method':'new-request-sonnet-8192-image-bound-v1','evidence_sha256':digest(EVIDENCE)}


class SonnetImageReservationMixin:
    def reservation(self,body):
        if body['model']==MODEL:return sonnet_reservation_detail(self,body)['reserved_usd']
        return super().reservation(body)
