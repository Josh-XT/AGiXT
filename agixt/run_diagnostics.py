#!/usr/bin/env python3
"""
Quick diagnostic runner for AGiXT backend issues
"""

import asyncio
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def run_quick_diagnostics():
    """Run a quick diagnostic check"""
    try:
        from diagnostics import SystemDiagnostics

        print("🔍 Running AGiXT Backend Diagnostics...")
        print("=" * 50)

        diagnostics = SystemDiagnostics()
        result = await diagnostics.run_diagnostics()

        # Display key metrics
        system = result.get("system", {})
        database = result.get("database", {})
        sessions = result.get("sessions", {})
        tasks = result.get("tasks", {})

        print(f"📊 System Status:")
        print(
            f"   Memory: {system.get('memory_mb', 0):.1f}MB ({system.get('memory_percent', 0):.1f}%)"
        )
        print(f"   CPU: {system.get('cpu_percent', 0):.1f}%")
        print(f"   Threads: {system.get('thread_count', 0)}")

        print(f"\n💾 Database Pool:")
        print(f"   Utilization: {database.get('utilization_percent', 0):.1f}%")
        print(
            f"   Active: {database.get('checked_out', 0)}/{database.get('pool_size', 0)}"
        )
        print(f"   Available: {database.get('available', 0)}")
        print(f"   Healthy: {'✅' if database.get('connection_healthy') else '❌'}")

        print(f"\n🔗 Sessions:")
        print(f"   Active: {sessions.get('active_sessions', 0)}")
        print(f"   Leaked: {sessions.get('leaked_sessions', 0)}")
        print(f"   Health Score: {sessions.get('health_score', 0):.1f}/100")

        print(f"\n⚙️  Tasks:")
        print(f"   Total: {tasks.get('total_tasks', 0)}")
        print(f"   Long-running: {tasks.get('long_running_tasks', 0)}")
        print(f"   Stuck: {tasks.get('stuck_tasks', 0)}")

        # Show recommendations
        recommendations = result.get("recommendations", [])
        if recommendations:
            print(f"\n⚠️  Recommendations:")
            for rec in recommendations:
                print(f"   • {rec}")
        else:
            print(f"\n✅ No issues detected!")

        # Check for critical issues
        critical_issues = []
        if database.get("utilization_percent", 0) > 90:
            critical_issues.append("Database pool near exhaustion")
        if sessions.get("leaked_sessions", 0) > 10:
            critical_issues.append("Excessive session leaks")
        if tasks.get("stuck_tasks", 0) > 0:
            critical_issues.append("Stuck tasks detected")

        if critical_issues:
            print(f"\n🚨 CRITICAL ISSUES:")
            for issue in critical_issues:
                print(f"   ❗ {issue}")

        return result

    except Exception as e:
        print(f"❌ Error running diagnostics: {e}")
        return None


if __name__ == "__main__":
    asyncio.run(run_quick_diagnostics())
