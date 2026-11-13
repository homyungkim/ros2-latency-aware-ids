"""ROSPaCe_reduced 층화 표본 추출 (연구실 PC에서 실행)

사용법 (명령 프롬프트):
    python rospace_sample.py "D:\\IIoT 원격 제어 NW IDS\\05_데이터\\ROSPaCe" 600000

- 첫 번째 인자: ROSPaCe_reduced.tar.gz 를 압축 해제한 폴더 (하위 폴더의 CSV 까지 모두 찾음)
- 두 번째 인자: 뽑을 전체 행 수 (기본 600000)
- 결과: 같은 폴더에 rospace_sample_<행수>.csv 생성 -> 이 파일 하나만 Kaggle 에 업로드

1차로 레이블 열만 읽어 클래스별 개수를 세고, 2차로 청크 단위로 읽으며
클래스별 비율에 맞춰 무작위 추출한다. 소수 클래스는 최소 MIN_PER_CLASS 행을 보장한다.
메모리는 청크 크기(20만 행) 정도만 사용한다.
"""
import glob
import os
import re
import sys

import numpy as np
import pandas as pd

CHUNK = 200_000
MIN_PER_CLASS = 20_000
SEED = 0


def find_label(cols):
    for c in cols:
        if c.strip().lower() in ("label", "class", "attack", "attack_type", "category"):
            return c
    raise SystemExit(f"레이블 열을 찾지 못했습니다. 열 목록: {list(cols)[:20]} ...")


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    target = int(sys.argv[2]) if len(sys.argv) > 2 else 600_000
    files = [f for f in glob.glob(os.path.join(root, "**", "*.csv*"), recursive=True)
             if "rospace_sample" not in os.path.basename(f) and f.strip().endswith(".csv")]
    num = lambda f: int(re.findall(r"(\d+)", os.path.basename(f))[-1]) if re.findall(r"\d+", os.path.basename(f)) else -1
    files.sort(key=num)
    if not files:
        raise SystemExit("CSV 파일이 없습니다. tar.gz 압축을 먼저 풀어 주세요.")
    print(f"CSV {len(files)}개 발견")
    # ROSPaCe_reduced 는 하나의 CSV 를 15 조각으로 나눈 것이라 첫 파일(_0)에만 헤더가 있다.
    cols = list(pd.read_csv(files[0], nrows=5).columns)
    label = find_label(cols)
    print("레이블 열:", label, "| 열 수:", len(cols))

    def has_header(f):
        with open(f, encoding="utf-8", errors="ignore") as fh:
            return fh.readline().strip().split(",")[0] == cols[0]

    def reader(f, **kw):
        if has_header(f):
            return pd.read_csv(f, low_memory=False, **kw)
        return pd.read_csv(f, header=None, names=cols, low_memory=False, **kw)

    # 1차: 클래스별 개수
    counts = pd.Series(dtype="int64")
    for f in files:
        for ch in reader(f, usecols=[label], chunksize=CHUNK * 5):
            counts = counts.add(ch[label].astype(str).value_counts(), fill_value=0)
        print("  집계 완료:", os.path.basename(f))
    counts = counts.astype(int)
    total = int(counts.sum())
    print("전체 행 수:", total)
    print(counts.sort_values(ascending=False))

    # 클래스별 추출 확률: 비례 할당 + 최소 보장
    quota = (counts / total * target).clip(lower=MIN_PER_CLASS)
    quota = np.minimum(quota, counts)
    prob = (quota / counts).to_dict()
    print("클래스별 목표 행 수:\n", quota.round().astype(int))

    rng = np.random.default_rng(SEED)
    out = os.path.join(root, f"rospace_sample_{target}.csv")
    first = True
    for f in files:
        for ch in reader(f, chunksize=CHUNK):
            p = ch[label].astype(str).map(prob).fillna(0).to_numpy()
            keep = ch[rng.random(len(ch)) < p]
            keep.to_csv(out, mode="w" if first else "a", header=first, index=False)
            first = False
        print("  추출 완료:", os.path.basename(f))
    n = sum(1 for _ in open(out, encoding="utf-8", errors="ignore")) - 1
    print(f"완료: {out} ({n:,} 행, {os.path.getsize(out) / 1e6:.0f} MB)")


if __name__ == "__main__":
    main()
