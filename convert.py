from pathlib import Path

# 최상위 데이터셋 폴더 경로를 입력하세요. (예: './my_dataset')
root_folder_path = './데이터셋_폴더명'

# .rglob()을 사용하면 하위 폴더 깊이에 상관없이 모든 .csv 파일을 찾아줍니다.
csv_files = Path(root_folder_path).rglob('*.csv')

for file_path in csv_files:
    try:
        # 1. 기존 인코딩(GB18030)으로 파일 내용 읽기
        with open(file_path, 'r', encoding='GB18030') as f:
            content = f.read()
        
        # 2. 동일한 파일에 UTF-8 인코딩으로 덮어쓰기
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
            
        print(f"✅ 변환 완료: {file_path}")
        
    except UnicodeDecodeError:
        # 이미 UTF-8이거나 다른 인코딩인 경우 건너뜀
        print(f"⚠️ 인코딩 불일치 (이미 변환되었을 수 있음): {file_path}")
    except Exception as e:
        print(f"❌ 오류 발생 ({file_path}): {e}")

print("모든 작업이 완료되었습니다.")