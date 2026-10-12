from pathlib import Path
import os

# 1. 현재 폴더 확인
current_dir = Path.cwd()
print(f"📂 현재 작업 폴더: {current_dir}")

# 2. CSV 파일 전체 찾기
csv_files = list(current_dir.rglob('*.csv'))
print(f"🔍 찾은 CSV 파일 개수: {len(csv_files)}개\n" + "-"*30)

success_count = 0

for file_path in csv_files:
    try:
        # cp949(한국어)로 시도해보고, 안 되면 utf-8로 읽도록 이중 처리
        try:
            with open(file_path, 'r', encoding='cp949') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        
        # utf-8-sig (BOM 포함 UTF-8)로 강제 덮어쓰기
        # 파일 맨 앞에 보이지 않는 기호가 들어가서 Git이 무조건 변경을 인식하게 됨!
        with open(file_path, 'w', encoding='utf-8-sig') as f:
            f.write(content)
            
        print(f"✅ 강제 변환 성공: {file_path.name}")
        success_count += 1
        
    except Exception as e:
        print(f"❌ 오류 발생 ({file_path.name}): {e}")

print("-" * 30)
print(f"🎉 총 {len(csv_files)}개 중 {success_count}개 파일 변환 완료!")