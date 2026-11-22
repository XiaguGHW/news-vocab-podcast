"""Illustrated recall videos. No practice results are inferred from generation."""
import argparse
import asyncio
import hashlib
import json
import re
import subprocess
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from build_story import font, run, duration, ROOT
from video import wrap

VOICES = {'zh':'zh-CN-XiaoxiaoNeural','en':'en-US-AvaNeural','de':'de-DE-KatjaNeural'}
BG, TEXT, MUTED, ACCENT = '#11151b','#f0f4fa','#bac2cf','#b6a4df'
RATES = ('-20%','-20%','-10%')


def validate(data, check_images=True):
    if data.get('schema_version') != 1 or not re.fullmatch(r'[A-Za-z0-9_-]+',data.get('id','')):
        raise ValueError('Invalid review schema/id')
    date.fromisoformat(data['date'])
    if datetime.fromisoformat(data['pub']).utcoffset() is None:
        raise ValueError('pub must include timezone')
    if not data.get('title') or not data.get('words'):
        raise ValueError('Missing review title/words')
    ids=set()
    for w in data['words']:
        for field in ('en','de','zh','ipa','question','example','translation','image','learning_id'):
            if not isinstance(w.get(field),str) or not w[field].strip():
                raise ValueError(f'Missing {field}')
        if w['learning_id'] in ids:
            raise ValueError('Duplicate review word')
        ids.add(w['learning_id'])
        for field in ('question','translation','zh'):
            if re.search('[A-Za-zÀ-ÿ]',w[field]):
                raise ValueError(f'Latin letters in Chinese {field}')
        if re.search('[\u3400-\u9fff]',w['example']):
            raise ValueError('Chinese in English example')
        img=(ROOT/w['image']).resolve()
        if not img.is_relative_to(ROOT/'assets'/'review'):
            raise ValueError('Image must be in assets/review')
        if check_images:
            with Image.open(img) as im:im.verify()


def plan(data):
    out=[dict(l='zh',t=f"本期复习{len(data['words'])}个词。每题留三秒，先想答案，再听例句。",phase='intro',pause=.5,index=0)]
    for i,w in enumerate(data['words']):
        out.extend([
            dict(l='zh',t=w['question'],phase='question',pause=3,index=i),
            dict(l='en',t=w.get('spoken',w['en']+'.'),phase='example',pause=.4,index=i),
            dict(l='de',t=w['de']+'.',phase='example',pause=.4,index=i),
            dict(l='zh',t=w['zh'].replace('；','，')+'。',phase='example',pause=.6,index=i),
        ])
        out.extend(dict(l='en',t=w['example'],phase='example',pause=.9 if n<2 else .6,
                        rate=rate,index=i,rep=n+1) for n,rate in enumerate(RATES))
        out.append(dict(l='zh',t=w['translation'],phase='example',pause=1.5,index=i))
    return out


def block(d,text,x,y,size,width,color=TEXT,bold=False,gap=10):
    f=font(size,bold)
    for paragraph in text.splitlines():
        for line in wrap(paragraph,f,width):
            d.text((x,y),line,font=f,fill=color);y+=size+gap
    return y


def card(data,s,dest,count=None):
    im=Image.new('RGB',(720,1280),BG);d=ImageDraw.Draw(im)
    d.text((48,35),'RECALL & REMEMBER',font=font(21,True),fill=ACCENT)
    block(d,data['title'].split('｜')[0],48,78,27,624,bold=True)
    d.line((48,138,672,138),fill='#384253',width=2)
    i=s['index'];w=data['words'][i]
    if s['phase']=='intro':
        block(d,'先想，再揭晓',58,340,48,600,bold=True)
        block(d,f"本期 {len(data['words'])} 个词\n每题三秒回忆。\n例句：英语三遍，中文一遍。",58,470,31,594,MUTED,gap=18)
    else:
        d.text((48,162),f"{i+1:02d} / {len(data['words']):02d}",font=font(22,True),fill=ACCENT)
        if s['phase']=='question':
            d.rounded_rectangle((40,230,680,1060),radius=24,fill='#1d2430')
            d.text((70,267),'情境回忆',font=font(26,True),fill=ACCENT)
            bottom=block(d,w['question'],70,374,36,580,bold=True,gap=18)
            if bottom>855:raise ValueError('Question overflows')
            d.text((70,925),'先说出英语，再听答案',font=font(28),fill=MUTED)
            if count:
                d.ellipse((299,1090,421,1212),fill=ACCENT)
                d.text((360,1148),str(count),font=font(56,True),fill=BG,anchor='mm')
        else:
            size=60
            while font(size,True).getlength(w['en'])>624:size-=2
            d.text((48,212),w['en'],font=font(size,True),fill='#9cc6ff')
            ipa=ImageFont.truetype(str(ROOT/'fonts'/'DejaVuSans.ttf'),26)
            d.text((50,291),w['ipa'],font=ipa,fill=MUTED)
            block(d,w['zh'],48,337,28,624,bold=True)
            block(d,w['de'],48,391,23,624,ACCENT)
            with Image.open(ROOT/w['image']) as picture:
                picture=picture.convert('RGB').resize((550,550),Image.Resampling.LANCZOS)
                im.paste(picture,(85,456))
            d.text((48,1023),'例句',font=font(19,True),fill=ACCENT)
            for size in range(30,23,-1):
                ef,zf=font(size,True),font(size-4)
                need=len(wrap(w['example'],ef,624))*(size+8)+len(wrap(w['translation'],zf,624))*(size+4)+15
                if need<193:break
            y=block(d,w['example'],48,1060,size,624,bold=True,gap=8)
            y=block(d,w['translation'],48,y+15,size-4,624,MUTED,gap=8)
            if y>1255:raise ValueError('Example overflows')
    im.save(dest)


async def synthesize(segments,folder,cache):
    import edge_tts
    sem=asyncio.Semaphore(3);locks={}
    cache.mkdir(parents=True,exist_ok=True)
    async def one(i,s):
        voice=VOICES[s['l']];rate=s.get('rate','+0%' if s['l']=='zh' else '-20%')
        key=hashlib.sha256(json.dumps([voice,s['t'],rate],ensure_ascii=False).encode()).hexdigest()
        raw=cache/f'{key}.mp3'
        async with locks.setdefault(key,asyncio.Lock()):
            if not raw.exists():
                async with sem:
                    for attempt in range(4):
                        partial=raw.with_suffix('.partial.mp3')
                        try:
                            await edge_tts.Communicate(s['t'],voice,rate=rate).save(str(partial))
                            if duration(partial)<=0:raise ValueError('Empty speech')
                            partial.replace(raw);break
                        except Exception:
                            partial.unlink(missing_ok=True)
                            if attempt==3:raise
                            await asyncio.sleep(2*(attempt+1))
        s['spoken_duration']=duration(raw)
        wav=folder/f'audio-{i:04d}.wav'
        run('ffmpeg','-y','-i',str(raw),'-af',f"apad=pad_dur={s['pause']}",'-ar','24000','-ac','1',str(wav))
        s['duration']=duration(wav);s['voice']=voice;s['rate']=rate
        if i%16==0:print(f'Audio {i+1}/{len(segments)}',flush=True)
    await asyncio.gather(*(one(i,s) for i,s in enumerate(segments)))


def build(data,output_dir,cache,render_only=False):
    validate(data,check_images=not render_only)
    folder=output_dir/data['id'];folder.mkdir(parents=True,exist_ok=True)
    segments=plan(data)
    # Render every unique card before incurring speech cost; no truncation.
    for s in segments:
        name=f"{s['phase']}-{s['index']:03d}.png"
        path=folder/name
        if not path.exists() and (not render_only or s['phase']!='example'):
            card(data,s,path)
    if render_only:return folder
    asyncio.run(synthesize(segments,folder,cache))
    frames=[];start=0
    for s in segments:
        path=folder/f"{s['phase']}-{s['index']:03d}.png"
        if s['phase']=='question':
            frames.append((path,s['spoken_duration']))
            for count in range(3,0,-1):
                p=folder/f"count-{s['index']:03d}-{count}.png";card(data,s,p,count)
                frames.append((p,1))
        else:frames.append((path,s['duration']))
        s.update(start=start,end=start+s['duration']);start+=s['duration']
    (folder/'timeline.json').write_text(json.dumps({'duration':start,'segments':segments},ensure_ascii=False,indent=2))
    (folder/'audio.txt').write_text(''.join(f"file '{folder/f'audio-{i:04d}.wav'}'\n" for i in range(len(segments))))
    (folder/'frames.txt').write_text(''.join(f"file '{p}'\nduration {t:.6f}\n" for p,t in frames)+f"file '{frames[-1][0]}'\n")
    wav=folder/'audio.wav'
    run('ffmpeg','-y','-f','concat','-safe','0','-i',str(folder/'audio.txt'),'-af','loudnorm=I=-16:TP=-1.5:LRA=11','-c:a','pcm_s16le',str(wav))
    mp3,mp4=folder/(data['id']+'.mp3'),folder/(data['id']+'.mp4')
    run('ffmpeg','-y','-i',str(wav),'-c:a','libmp3lame','-b:a','128k',str(mp3))
    run('ffmpeg','-y','-f','concat','-safe','0','-i',str(folder/'frames.txt'),'-i',str(wav),'-t',str(start),'-vf','fps=10,format=yuv420p','-c:v','libx264','-preset','veryfast','-tune','stillimage','-crf','23','-c:a','aac','-b:a','192k','-movflags','+faststart',str(mp4))
    print(json.dumps({'id':data['id'],'seconds':start,'folder':str(folder)}),flush=True)
    return folder


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('source',type=Path)
    p.add_argument('--output-dir',type=Path,default=ROOT/'dist'/'reviews')
    p.add_argument('--cache-dir',type=Path,default=ROOT/'.cache'/'review-tts')
    p.add_argument('--check',action='store_true');p.add_argument('--render-only',action='store_true')
    args=p.parse_args();data=json.loads(args.source.read_text())
    if args.check:validate(data);print('OK: review checked')
    else:build(data,args.output_dir.resolve(),args.cache_dir.resolve(),args.render_only)
