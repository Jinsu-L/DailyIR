import os
import subprocess
import argparse
import shutil
import logging
import re
from datetime import datetime

def run_command(command, cwd=None):
    """주어진 디렉토리에서 셸 명령어를 실행하고 결과를 로깅합니다."""
    if cwd is None:
        cwd = os.getcwd()
    logging.info(f"Executing command: {' '.join(command)}")
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=True, cwd=cwd)
        if result.stdout.strip():
            logging.info(f"Stdout: {result.stdout.strip()}")
        if result.stderr.strip():
            logging.info(f"Stderr: {result.stderr.strip()}")
        return result.stdout
    except subprocess.CalledProcessError as e:
        logging.error(f"Command failed with return code {e.returncode}")
        if e.stderr.strip():
            logging.error(f"Stderr: {e.stderr.strip()}")
        raise

def find_report(report_dir: str, report_date: str | None = None) -> tuple[str | None, str | None]:
    """리포트 디렉토리에서 특정 날짜 또는 가장 최신 .md 파일을 찾습니다."""
    if not os.path.exists(report_dir):
        logging.warning(f"Report directory '{report_dir}' not found.")
        return None, None

    if report_date:
        report_filename = f"{report_date}.md"
        report_path = os.path.join(report_dir, report_filename)
        if os.path.exists(report_path):
            logging.info(f"Found specified report: {report_filename}")
            return report_path, report_filename
        else:
            logging.error(f"Specified report file not found: {report_path}")
            return None, None
    else:
        report_files = [f for f in os.listdir(report_dir) if f.endswith('.md')]
        if not report_files:
            logging.info("No markdown report files found.")
            return None, None
        
        latest_report_name = sorted(report_files, reverse=True)[0]
        report_path = os.path.join(report_dir, latest_report_name)
        logging.info(f"Found latest report: {latest_report_name}")
        return report_path, latest_report_name

def find_data_files(data_dir: str, report_date: str) -> tuple[str | None, str | None]:
    """데이터 디렉토리에서 특정 날짜의 크롤링 및 스코어 파일을 찾습니다."""
    crawled_file = f"{report_date}.json"
    scores_file = f"{report_date}-scores.json"

    crawled_path = os.path.join(data_dir, 'crawled', crawled_file)
    scores_path = os.path.join(data_dir, 'scores', scores_file)

    if not os.path.exists(crawled_path):
        logging.warning(f"Crawled data file not found: {crawled_path}")
        crawled_path = None

    if not os.path.exists(scores_path):
        logging.warning(f"Scores data file not found: {scores_path}")
        scores_path = None

    return crawled_path, scores_path

def parse_readme(content: str) -> dict:
    """README 콘텐츠를 파싱하여 연도/월별 링크 데이터를 담은 딕셔너리로 변환합니다."""
    data = {}
    current_year, current_month = None, None
    for line in content.splitlines():
        year_match = re.match(r"^##\s+(\d{4})", line)
        month_match = re.match(r"^###\s+([A-Za-z]+)", line)
        link_match = re.match(r"^\s*-\s*\[.*\]\(.*\)", line)

        if year_match:
            current_year = year_match.group(1)
            data[current_year] = {}
        elif month_match and current_year:
            current_month = month_match.group(1)
            data[current_year][current_month] = []
        elif link_match and current_year and current_month:
            data[current_year][current_month].append(line)
    return data

def regenerate_readme(data: dict) -> str:
    """파싱된 데이터 딕셔너리를 사용하여 README 콘텐츠를 다시 생성합니다."""
    content = "# Daily Information Retrieval Papers\n\nA curated list of daily papers related to Information Retrieval.\n"
    sorted_years = sorted(data.keys(), reverse=True)
    
    month_name_to_num = {datetime.strptime(str(i), '%m').strftime('%B'): i for i in range(1, 13)}

    for year in sorted_years:
        content += f"\n## {year}\n"
        sorted_months = sorted(data[year].keys(), key=lambda m: month_name_to_num.get(m, 0), reverse=True)

        for month in sorted_months:
            content += f"\n### {month}\n"
            content += "\n".join(data[year][month])
            content += "\n"
    return content

def upload_to_same_repo(target_date: datetime.date, project_root: str):
    """동일 저장소 내에서 PAPERS.md 업데이트 및 Git 커밋을 수행합니다."""
    logging.info("--- Uploading to same repository ---")
    
    date_str = target_date.strftime("%Y-%m-%d")
    year_str = target_date.strftime('%Y')
    month_name = target_date.strftime('%B')
    month_folder = target_date.strftime('%Y-%m')
    
    # PAPERS.md 파일 경로
    papers_path = os.path.join(project_root, 'PAPERS.md')
    
    try:
        # 기존 PAPERS.md 읽기
        papers_content = ""
        if os.path.exists(papers_path):
            with open(papers_path, 'r', encoding='utf-8') as f:
                papers_content = f.read()
        
        # 새로운 링크 라인 생성
        new_link_line = f"- [{date_str}](./reports/{month_folder}/{date_str}.md)"
        
        # 이미 링크가 존재하는지 확인
        if new_link_line not in papers_content:
            logging.info("Adding new link to PAPERS.md")
            data = parse_readme(papers_content)
            data.setdefault(year_str, {}).setdefault(month_name, []).insert(0, new_link_line)
            new_papers_content = regenerate_readme(data)
            
            with open(papers_path, 'w', encoding='utf-8') as f:
                f.write(new_papers_content)
            logging.info("PAPERS.md updated successfully")
        else:
            logging.info("Link already exists in PAPERS.md. Skipping PAPERS.md update.")
        
        # Git 상태 확인
        try:
            status_output = run_command(['git', 'status', '--porcelain'], cwd=project_root)
            if not status_output.strip():
                logging.info("No changes to commit. All files are already up-to-date.")
                return
            
            logging.info("Changes detected. Adding files to Git...")
            
            # Git add
            run_command(['git', 'add', 'reports/', 'data/', 'PAPERS.md'], cwd=project_root)
            
            # Git commit
            commit_message = f"Add report and data for {date_str}"
            run_command(['git', 'commit', '-m', commit_message], cwd=project_root)
            
            # Git push
            run_command(['git', 'push', 'origin', 'main'], cwd=project_root)
            
            logging.info(f"Successfully committed and pushed changes for {date_str}")
            
        except subprocess.CalledProcessError as e:
            if "nothing to commit" in str(e.stderr):
                logging.info("No changes to commit. All files are already up-to-date.")
            else:
                logging.error(f"Git command failed: {e}")
                raise
                
    except Exception as e:
        logging.error(f"Failed to update PAPERS.md and commit changes: {e}", exc_info=True)

def main():
    """메인 업로드 로직 - 동일 저장소 내에서 처리"""
    parser = argparse.ArgumentParser(description="동일 저장소 내에서 리포트를 업로드하고 PAPERS.md를 업데이트합니다.")
    parser.add_argument("--report-date", required=True, help="업로드할 리포트의 날짜 (YYYY-MM-DD)")
    parser.add_argument("--project-root", default=".", help="프로젝트 루트 디렉토리")
    args = parser.parse_args()

    try:
        report_date_obj = datetime.strptime(args.report_date, '%Y-%m-%d').date()
    except ValueError:
        logging.error(f"Invalid date format: {args.report_date}. Expected YYYY-MM-DD")
        return

    project_root = os.path.abspath(args.project_root)
    upload_to_same_repo(report_date_obj, project_root)
    logging.info("Upload process completed successfully")

if __name__ == "__main__":
    # 로깅 설정 추가
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    main()