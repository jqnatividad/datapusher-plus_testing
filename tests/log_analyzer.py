#!/usr/bin/env python3
"""
DataPusher Plus Worker Log Analyzer
Analyzes CKAN worker logs and generates insights for test reporting
"""

import re
import csv
import sys
import statistics
from pathlib import Path
from datetime import datetime

def parse_worker_logs(log_file_path):
    """Parse worker logs and extract job information"""
    try:
        with open(log_file_path, 'r') as f:
            log_content = f.read()
    except FileNotFoundError:
        print(f"Log file not found: {log_file_path}")
        return []
    except Exception as e:
        print(f"Error reading log file: {e}")
        return []

    # Split log into individual job entries by looking for job start pattern
    # Pattern: timestamp INFO [job_id] Setting log level to INFO
    job_pattern = r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) INFO\s+\[([a-f0-9-]{36})\] Setting log level to INFO'
    
    # Find all job starts
    job_starts = list(re.finditer(job_pattern, log_content))
    processed_jobs = []

    for i, match in enumerate(job_starts):
        job_start_pos = match.start()
        job_end_pos = job_starts[i + 1].start() if i + 1 < len(job_starts) else len(log_content)
        
        entry = log_content[job_start_pos:job_end_pos]
        
        # Extract timestamp and job ID from the match
        timestamp_str = match.group(1)
        job_id = match.group(2)

        # Convert timestamp to standard format
        try:
            dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S,%f')
            timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
        except:
            timestamp = timestamp_str

        # Extract file information
        file_url_match = re.search(r'Fetching from: (.+)', entry)
        file_url = file_url_match.group(1).strip() if file_url_match else "unknown"
        file_name = file_url.split('/')[-1] if file_url != "unknown" else "unknown"

        # Determine job status
        if "DATAPUSHER+ JOB DONE!" in entry:
            status = "SUCCESS"
        elif "ckanext.datapusher_plus.utils.JobError:" in entry:
            status = "ERROR"
        else:
            status = "INCOMPLETE"

        # Extract QSV version
        qsv_version_match = re.search(r'qsv version found: ([\d.]+)', entry)
        qsv_version = qsv_version_match.group(1) if qsv_version_match else ""

        # Extract file format
        file_format_match = re.search(r'File format: (\w+)', entry)
        file_format = file_format_match.group(1) if file_format_match else ""

        # Extract encoding
        encoding_match = re.search(r'Identified encoding of the file: (\w+)', entry)
        encoding = encoding_match.group(1) if encoding_match else ""

        # Check normalization
        normalized = "Successful" if "Normalized & transcoded" in entry else "Failed"

        # Check if valid CSV
        valid_csv = "TRUE" if "Well-formed, valid CSV file confirmed" in entry else "FALSE"

        # Check if sorted
        sorted_match = re.search(r'Sorted: (True|False)', entry)
        sorted_status = sorted_match.group(1).upper() if sorted_match else "UNKNOWN"

        # Check database safe headers
        unsafe_headers_match = re.search(r'"(\d+) unsafe" header names found', entry)
        if unsafe_headers_match:
            unsafe_count = int(unsafe_headers_match.group(1))
            db_safe_headers = f"{unsafe_count} unsafe headers found"
        elif "No unsafe header names found" in entry:
            db_safe_headers = "All headers safe"
        else:
            db_safe_headers = "Unknown"

        # Check analysis status
        analysis_match = re.search(r'ANALYSIS DONE! Analyzed and prepped in ([\d.]+) seconds', entry)
        analysis_status = "Successful" if analysis_match else "Failed"

        # Extract records detected
        records_match = re.search(r'(\d+)\s+records detected', entry)
        records_processed = int(records_match.group(1)) if records_match else 0

        # Extract timing information
        timings = {
            'total_time': 0.0,
            'download_time': 0.0,
            'analysis_time': 0.0,
            'copying_time': 0.0,
            'indexing_time': 0.0,
            'formulae_time': 0.0,
            'metadata_time': 0.0
        }

        # Parse timing breakdown from the job summary
        total_time_match = re.search(r'TOTAL ELAPSED TIME: ([\d.]+)', entry)
        if total_time_match:
            timings['total_time'] = float(total_time_match.group(1))

        download_match = re.search(r'Download: ([\d.]+)', entry)
        if download_match:
            timings['download_time'] = float(download_match.group(1))

        analysis_match = re.search(r'Analysis: ([\d.]+)', entry)
        if analysis_match:
            timings['analysis_time'] = float(analysis_match.group(1))

        copying_match = re.search(r'COPYing: ([\d.]+)', entry)
        if copying_match:
            timings['copying_time'] = float(copying_match.group(1))

        indexing_match = re.search(r'Indexing: ([\d.]+)', entry)
        if indexing_match:
            timings['indexing_time'] = float(indexing_match.group(1))

        formulae_match = re.search(r'Formulae processing: ([\d.]+)', entry)
        if formulae_match:
            timings['formulae_time'] = float(formulae_match.group(1))

        metadata_match = re.search(r'Resource metadata updates: ([\d.]+)', entry)
        if metadata_match:
            timings['metadata_time'] = float(metadata_match.group(1))

        # Extract rows copied
        rows_copied_match = re.search(r'Copied (\d+) rows to', entry)
        rows_copied = int(rows_copied_match.group(1)) if rows_copied_match else 0

        # Extract columns indexed
        indexed_match = re.search(r'Indexed (\d+) column/s', entry)
        columns_indexed = int(indexed_match.group(1)) if indexed_match else 0

        # Extract specific DataPusher Plus error
        error_type = ""
        error_message = ""

        if status == "ERROR":
            # Look for specific DataPusher Plus JobError
            dp_error_match = re.search(r'ckanext\.datapusher_plus\.utils\.JobError: (.+?)(?:\n|$)', entry)
            if dp_error_match:
                error_message = dp_error_match.group(1).strip()
                # Classify error type based on message content
                if "invalid Zip archive" in error_message or "EOCD" in error_message:
                    error_type = "CORRUPTED_EXCEL"
                elif "qsv command failed" in error_message:
                    error_type = "QSV_ERROR"
                elif "Only http, https, and ftp resources may be fetched" in error_message:
                    error_type = "INVALID_URL"
                else:
                    error_type = "DATAPUSHER_ERROR"
            else:
                error_type = "UNKNOWN_ERROR"
                error_message = "Unknown DataPusher error"

        # Only add jobs that have valid job IDs and meaningful data
        if job_id and job_id != "unknown":
            processed_jobs.append({
                'timestamp': timestamp,
                'job_id': job_id,
                'file_name': file_name,
                'status': status,
                'qsv_version': qsv_version,
                'file_format': file_format,
                'encoding': encoding,
                'normalized': normalized,
                'valid_csv': valid_csv,
                'sorted': sorted_status,
                'db_safe_headers': db_safe_headers,
                'analysis': analysis_status,
                'records': records_processed,
                'total_time': timings['total_time'],
                'download_time': timings['download_time'],
                'analysis_time': timings['analysis_time'],
                'copying_time': timings['copying_time'],
                'indexing_time': timings['indexing_time'],
                'formulae_time': timings['formulae_time'],
                'metadata_time': timings['metadata_time'],
                'rows_copied': rows_copied,
                'columns_indexed': columns_indexed,
                'error_type': error_type,
                'error_message': error_message.replace('"', '""') if error_message else ""  # Escape quotes for CSV
            })

    return processed_jobs

def write_worker_analysis(jobs, output_file):
    """Write job analysis to CSV file"""
    fieldnames = ['timestamp', 'job_id', 'file_name', 'status', 'qsv_version', 'file_format', 
                  'encoding', 'normalized', 'valid_csv', 'sorted', 'db_safe_headers', 'analysis',
                  'records', 'total_time', 'download_time', 'analysis_time', 'copying_time', 
                  'indexing_time', 'formulae_time', 'metadata_time', 'rows_copied', 'columns_indexed',
                  'error_type', 'error_message']
    
    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(jobs)

def generate_performance_insights(jobs):
    """Generate performance insights from job data"""
    successful_jobs = [job for job in jobs if job['status'] == 'SUCCESS']
    error_jobs = [job for job in jobs if job['status'] == 'ERROR']
    
    insights = []
    
    if successful_jobs:
        # Calculate performance metrics
        total_times = [job['total_time'] for job in successful_jobs if job['total_time']]
        download_times = [job['download_time'] for job in successful_jobs if job['download_time']]
        analysis_times = [job['analysis_time'] for job in successful_jobs if job['analysis_time']]
        copying_times = [job['copying_time'] for job in successful_jobs if job['copying_time']]
        
        # Calculate data metrics
        total_records = sum(job['records'] for job in successful_jobs)
        total_rows_copied = sum(job['rows_copied'] for job in successful_jobs)
        total_columns_indexed = sum(job['columns_indexed'] for job in successful_jobs)
        
        insights.append(f"Total Records Processed: {total_records:,}")
        insights.append(f"Total Rows Imported: {total_rows_copied:,}")
        insights.append(f"Total Columns Indexed: {total_columns_indexed}")
        
        if total_times:
            avg_total = statistics.mean(total_times)
            fastest = min(total_times)
            slowest = max(total_times)
            insights.append(f"Average Processing Time: {avg_total:.2f}s")
            insights.append(f"Fastest File: {fastest:.2f}s")
            insights.append(f"Slowest File: {slowest:.2f}s")
            
            if total_records > 0:
                throughput = total_records / sum(total_times)
                insights.append(f"Processing Throughput: {throughput:,.0f} records/sec")
        
        if download_times:
            avg_download = statistics.mean(download_times)
            insights.append(f"Average Download Time: {avg_download:.2f}s")
        
        if analysis_times:
            avg_analysis = statistics.mean(analysis_times)
            insights.append(f"Average Analysis Time: {avg_analysis:.2f}s")
        
        if copying_times:
            avg_copying = statistics.mean(copying_times)
            insights.append(f"Average Copy Time: {avg_copying:.2f}s")

        # QSV version analysis
        qsv_versions = [job['qsv_version'] for job in successful_jobs if job['qsv_version']]
        if qsv_versions:
            unique_versions = list(set(qsv_versions))
            insights.append(f"QSV Versions Used: {', '.join(unique_versions)}")

        # File format analysis
        formats = [job['file_format'] for job in successful_jobs if job['file_format']]
        if formats:
            format_counts = {}
            for fmt in formats:
                format_counts[fmt] = format_counts.get(fmt, 0) + 1
            format_summary = ', '.join([f"{fmt}({count})" for fmt, count in format_counts.items()])
            insights.append(f"File Formats Processed: {format_summary}")
    
    # Error analysis
    if error_jobs:
        error_types = {}
        for job in error_jobs:
            error_type = job['error_type']
            error_types[error_type] = error_types.get(error_type, 0) + 1
        
        most_common_error = max(error_types, key=error_types.get)
        insights.append(f"Most Common Error: {most_common_error} ({error_types[most_common_error]} occurrences)")
        
        if 'CORRUPTED_EXCEL' in error_types:
            insights.append(f"Corrupted Excel Files: {error_types['CORRUPTED_EXCEL']}")
        
        if 'QSV_ERROR' in error_types:
            insights.append(f"QSV Processing Errors: {error_types['QSV_ERROR']}")
    
    return insights

def get_worker_insight_for_file(jobs, target_file):
    """Get worker insight string for a specific file"""
    for job in jobs:
        if target_file in job['file_name'] or job['file_name'] in target_file:
            if job['status'] == 'SUCCESS':
                records = job['records']
                total_time = job['total_time']
                phases = []
                if job['download_time'] > 0.1:
                    phases.append(f"DL:{job['download_time']:.1f}s")
                if job['analysis_time'] > 0.1:
                    phases.append(f"AN:{job['analysis_time']:.1f}s")
                if job['copying_time'] > 0.1:
                    phases.append(f"CP:{job['copying_time']:.1f}s")
                
                phase_info = "|".join(phases[:2])  # Limit to 2 phases
                if records > 0:
                    return f"{records}rec|{total_time:.1f}s|{phase_info}"
                else:
                    return f"{total_time:.1f}s|{phase_info}"
            elif job['status'] == 'ERROR':
                return f"ERROR:{job['error_type']}"
            break
    return "No worker data"

def main():
    if len(sys.argv) < 2:
        print("Usage: python log_analyzer.py <command> [args...]")
        print("Commands:")
        print("  analyze <log_file> <output_csv>")
        print("  insights <worker_csv>")
        print("  file-insight <worker_csv> <filename>")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "analyze":
        if len(sys.argv) < 4:
            print("Usage: python log_analyzer.py analyze <log_file> <output_csv>")
            sys.exit(1)
        
        log_file = sys.argv[2]
        output_csv = sys.argv[3]
        
        jobs = parse_worker_logs(log_file)
        write_worker_analysis(jobs, output_csv)
        print(f"Analyzed {len(jobs)} jobs from worker logs")
        
    elif command == "insights":
        if len(sys.argv) < 3:
            print("Usage: python log_analyzer.py insights <worker_csv>")
            sys.exit(1)
        
        worker_csv = sys.argv[2]
        
        jobs = []
        try:
            with open(worker_csv, 'r') as f:
                reader = csv.DictReader(f)
                jobs = list(reader)
                # Convert numeric fields
                for job in jobs:
                    for field in ['total_time', 'download_time', 'analysis_time', 'copying_time', 
                                  'indexing_time', 'formulae_time', 'metadata_time']:
                        job[field] = float(job[field]) if job[field] else 0.0
                    for field in ['records', 'rows_copied', 'columns_indexed']:
                        job[field] = int(job[field]) if job[field] else 0
        except FileNotFoundError:
            print("Worker analysis file not found")
            sys.exit(1)
        
        insights = generate_performance_insights(jobs)
        for insight in insights:
            print(insight)
    
    elif command == "file-insight":
        if len(sys.argv) < 4:
            print("Usage: python log_analyzer.py file-insight <worker_csv> <filename>")
            sys.exit(1)
        
        worker_csv = sys.argv[2]
        filename = sys.argv[3]
        
        jobs = []
        try:
            with open(worker_csv, 'r') as f:
                reader = csv.DictReader(f)
                jobs = list(reader)
                # Convert numeric fields
                for job in jobs:
                    for field in ['total_time', 'download_time', 'analysis_time', 'copying_time']:
                        job[field] = float(job[field]) if job[field] else 0.0
                    job['records'] = int(job['records']) if job['records'] else 0
        except FileNotFoundError:
            print("No worker data")
            sys.exit(0)
        
        insight = get_worker_insight_for_file(jobs, filename)
        print(insight)
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)

if __name__ == "__main__":
    main()
