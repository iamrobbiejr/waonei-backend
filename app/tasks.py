"""
WAONEI Traffic Violation Processing Tasks
Updated to work with your existing structure
"""

from app.worker import celery_app
from supabase import create_client, Client
import os
import sys
from datetime import datetime, timedelta, timezone

# Add a parent directory to a path to import detector
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from traffic_violation_detector import get_detector, ViolationResult

# Re-init supabase here (Celery workers are separate processes)
supabase: Client = create_client(
    os.getenv("SUPABASE_URL"),
    os.getenv("SUPABASE_SERVICE_ROLE_KEY")
)


@celery_app.task(name="app.tasks.process_violation", bind=True, max_retries=3)
def process_violation(self, report_id: str, file_url: str):
    """
    Process traffic violation using YOLOv8 AI detection

    Args:
        report_id: UUID of the report in a database
        file_url: URL to the uploaded image/video

    Returns:
        dict: Processing result
        :param file_url:
        :param report_id:
        :param self:
    """
    print(f"🚦 Starting AI analysis for Report #{report_id}...")
    print(f"📸 File URL: {file_url}")

    try:
        # Update status to processing
        supabase.table("reports").update({
            "status": "processing",
            "processing_started_at": datetime.now(timezone.utc).isoformat()
        }).eq("id", report_id).execute()

        # Get AI detector instance
        print(f"🤖 Initializing AI detector...")
        detector = get_detector()

        # Run AI analysis
        print(f"🔍 Running AI detection...")
        result: ViolationResult = detector.analyze_image(file_url)

        print(f"✅ Detection complete:")
        print(f"   - Violation: {result.violation_type}")
        print(f"   - Confidence: {result.confidence:.2%}")
        print(f"   - Status: {result.status}")

        # Determine final status based on a violation type
        if result.violation_type == 'none':
            final_status = 'no_violation'
        elif result.status == 'verified':
            final_status = 'verified'
        else:
            final_status = 'rejected'

        # Prepare update data
        update_data = {
            "status": final_status,
            "violation_type": result.violation_type,
            "confidence_score": float(result.confidence),
            "ai_analysis": result.details,
            "processing_completed_at": datetime.now(timezone.utc).isoformat(),
        }

        # Add a bounding box if available
        if result.bbox:
            update_data["detection_bbox"] = result.bbox

        # Calculate processing time
        report_data = supabase.table("reports").select("processing_started_at").eq("id", report_id).single().execute()
        if report_data.data and report_data.data.get('processing_started_at'):
            start_time = datetime.fromisoformat(report_data.data['processing_started_at'].replace('Z', '+00:00'))
            end_time = datetime.now(timezone.utc)
            processing_time = (end_time - start_time).total_seconds()
            update_data["processing_time_seconds"] = processing_time

        # Update database with AI results
        response = supabase.table("reports").update(update_data).eq("id", report_id).execute()

        print(f"💾 Database updated for Report #{report_id}")

        # Prepare return data
        return {
            "success": True,
            "report_id": report_id,
            "violation_type": result.violation_type,
            "confidence": float(result.confidence),
            "status": final_status,
            "message": f"Analysis complete: {result.details.get('description', 'Processed successfully')}"
        }

    except Exception as e:
        error_msg = f"AI processing failed: {str(e)}"
        print(f"❌ Error processing Report #{report_id}: {error_msg}")

        # Update database with error status
        try:
            supabase.table("reports").update({
                "status": "failed",
                "error_message": error_msg,
                "processing_completed_at": datetime.now(timezone.utc).isoformat()
            }).eq("id", report_id).execute()
        except Exception as db_error:
            print(f"Failed to update error status in DB: {db_error}")

        # Retry logic
        if self.request.retries < self.max_retries:
            print(f"🔄 Retrying... (Attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=e, countdown=60)  # Retry after 60 seconds

        return {
            "success": False,
            "report_id": report_id,
            "error": error_msg,
            "status": "failed"
        }


@celery_app.task(name="app.tasks.batch_process_violations")
def batch_process_violations(report_ids: list):
    """
    Process multiple violations in batch
    Useful for processing queued reports

    Args:
        report_ids: List of report UUIDs to process

    Returns:
        dict: Batch processing results
    """
    print(f"📦 Batch processing {len(report_ids)} reports...")

    results = []
    for report_id in report_ids:
        # Fetch report from database
        try:
            report = supabase.table("reports")\
                .select("id, file_url")\
                .eq("id", report_id)\
                .single()\
                .execute()

            if report.data:
                # Trigger individual processing
                result = process_violation.delay(
                    report.data['id'],
                    report.data['file_url']
                )
                results.append({
                    "report_id": report_id,
                    "task_id": result.id,
                    "status": "queued"
                })
        except Exception as e:
            print(f"Failed to queue report {report_id}: {e}")
            results.append({
                "report_id": report_id,
                "status": "error",
                "error": str(e)
            })

    return {
        "total": len(report_ids),
        "queued": len([r for r in results if r['status'] == 'queued']),
        "failed": len([r for r in results if r['status'] == 'error']),
        "results": results
    }


@celery_app.task(name="app.tasks.reprocess_failed_violations")
def reprocess_failed_violations():
    """
    Find and reprocess all failed violations
    Runs as a periodic task (every hour via beat schedule)

    Returns:
        dict: Reprocessing results
    """
    print("🔍 Looking for failed reports to reprocess...")

    try:
        # Get all failed reports from last 24 hours
        failed_reports = supabase.table("reports")\
            .select("id, file_url")\
            .eq("status", "failed")\
            .gte("created_at", (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat())\
            .limit(50)\
            .execute()

        if failed_reports.data:
            report_ids = [r['id'] for r in failed_reports.data]
            print(f"Found {len(report_ids)} failed reports. Reprocessing...")

            return batch_process_violations(report_ids)
        else:
            print("No failed reports found.")
            return {"message": "No failed reports to process"}

    except Exception as e:
        print(f"Error in reprocessing: {e}")
        return {"error": str(e)}


@celery_app.task(name="app.tasks.cleanup_old_pending")
def cleanup_old_pending():
    """
    Clean up old pending reports that never got processed
    Runs daily via beat schedule

    Reports pending for more than 24 hours are marked as 'expired'

    Returns:
        dict: Cleanup results
    """
    print("🧹 Cleaning up old pending reports...")

    try:
        # Find reports pending for more than 24 hours
        cutoff_time = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

        old_pending = supabase.table("reports")\
            .select("id")\
            .eq("status", "pending_analysis")\
            .lt("created_at", cutoff_time)\
            .execute()

        if old_pending.data:
            count = len(old_pending.data)

            # Mark as expired
            for report in old_pending.data:
                supabase.table("reports").update({
                    "status": "expired",
                    "error_message": "Report expired - not processed within 24 hours",
                    "processing_completed_at": datetime.now(timezone.utc).isoformat()
                }).eq("id", report['id']).execute()

            print(f"✅ Marked {count} old pending reports as expired")
            return {
                "success": True,
                "expired_count": count,
                "message": f"Marked {count} reports as expired"
            }
        else:
            print("No old pending reports found")
            return {
                "success": True,
                "expired_count": 0,
                "message": "No old pending reports"
            }

    except Exception as e:
        print(f"Error in cleanup: {e}")
        return {"error": str(e)}


@celery_app.task(name="app.tasks.get_processing_stats")
def get_processing_stats():
    """
    Get statistics about AI processing performance
    Useful for monitoring and optimization

    Returns:
        dict: Processing statistics
    """
    try:
        # Get all processed reports (last 7 days)
        week_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

        reports = supabase.table("reports")\
            .select("status, processing_time_seconds, confidence_score, violation_type")\
            .gte("created_at", week_ago)\
            .not_.eq("status", "pending_analysis")\
            .execute()

        if not reports.data:
            return {"message": "No processed reports in last 7 days"}

        stats = {
            "total_processed": len(reports.data),
            "by_status": {},
            "avg_processing_time": 0,
            "avg_confidence": 0,
            "by_violation_type": {}
        }

        processing_times = []
        confidence_scores = []

        for report in reports.data:
            # Status counts
            status = report.get('status')
            stats['by_status'][status] = stats['by_status'].get(status, 0) + 1

            # Processing times
            if report.get('processing_time_seconds'):
                processing_times.append(report['processing_time_seconds'])

            # Confidence scores
            if report.get('confidence_score'):
                confidence_scores.append(report['confidence_score'])

            # Violation types
            v_type = report.get('violation_type', 'unknown')
            stats['by_violation_type'][v_type] = stats['by_violation_type'].get(v_type, 0) + 1

        if processing_times:
            stats['avg_processing_time'] = sum(processing_times) / len(processing_times)
            stats['min_processing_time'] = min(processing_times)
            stats['max_processing_time'] = max(processing_times)

        if confidence_scores:
            stats['avg_confidence'] = sum(confidence_scores) / len(confidence_scores)

        return stats

    except Exception as e:
        print(f"Error getting stats: {e}")
        return {"error": str(e)}