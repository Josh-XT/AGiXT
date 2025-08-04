# AGiXT Worker Exhaustion Fix - Deployment Checklist

## Pre-Deployment Steps

- [ ] **Backup current system**
  - [ ] Database backup
  - [ ] Configuration files backup
  - [ ] Current logs backup

- [ ] **Review changes**
  - [ ] TaskMonitor.py improvements
  - [ ] Task.py resource management
  - [ ] Websearch.py task cleanup
  - [ ] Web browsing resource management
  - [ ] App.py lifecycle improvements
  - [ ] New ResourceMonitor.py
  - [ ] Updated requirements.txt

## Deployment Steps

1. **Stop AGiXT services**
   ```bash
   docker-compose down
   ```

2. **Update requirements**
   ```bash
   pip install -r requirements.txt
   # OR if using Docker:
   docker-compose build --no-cache
   ```

3. **Deploy updated code**
   - Replace modified files with updated versions
   - Add new files (ResourceMonitor.py, resource_config.py, diagnostics.py)

4. **Update environment variables** (optional but recommended)
   ```bash
   # Add to .env file or docker-compose.yml
   MAX_MEMORY_USAGE_MB=2048
   RESOURCE_CLEANUP_INTERVAL=600
   MAX_TASK_DURATION=3600
   LOG_RESOURCE_USAGE=true
   LOG_TASK_PERFORMANCE=true
   ```

5. **Start services**
   ```bash
   docker-compose up -d
   ```

## Post-Deployment Verification

- [ ] **Check service startup**
  ```bash
  docker-compose logs -f
  # Look for "AGiXT services started successfully"
  # Look for "Resource monitor started"
  ```

- [ ] **Run diagnostics**
  ```bash
  python diagnostics.py
  ```

- [ ] **Monitor resource usage**
  - [ ] Check memory usage trends
  - [ ] Monitor task completion rates
  - [ ] Watch for stuck tasks

- [ ] **Test basic functionality**
  - [ ] Create and run a simple task
  - [ ] Test web browsing extension
  - [ ] Test websearch functionality
  - [ ] Verify GraphQL subscriptions work

## Monitoring Schedule

### Immediate (first 24 hours)
- [ ] Check logs every 2 hours
- [ ] Run diagnostics every 6 hours
- [ ] Monitor memory usage

### Short-term (first week)
- [ ] Daily log review
- [ ] Daily diagnostics run
- [ ] Monitor for any hanging processes

### Long-term (ongoing)
- [ ] Weekly diagnostics
- [ ] Monthly resource usage review
- [ ] Quarterly cleanup maintenance

## Success Indicators

✅ **System no longer hangs requiring container restart**
✅ **Memory usage remains stable over time**
✅ **Tasks complete successfully without timing out**
✅ **Resource monitor shows healthy status**
✅ **No accumulation of stuck tasks**
✅ **Browser instances are properly cleaned up**
✅ **Database connections don't leak**

## Rollback Plan (if needed)

1. **Stop services**
   ```bash
   docker-compose down
   ```

2. **Restore backup files**
   - Restore original Python files
   - Remove new files (ResourceMonitor.py, etc.)
   - Restore original requirements.txt

3. **Start services**
   ```bash
   docker-compose up -d
   ```

## Troubleshooting

### If services fail to start:
1. Check logs: `docker-compose logs`
2. Verify Python syntax: `python -m py_compile <file>`
3. Check imports: Run diagnostics script to verify dependencies

### If performance issues persist:
1. Run diagnostics to identify bottlenecks
2. Increase resource limits in environment variables
3. Reduce UVICORN_WORKERS if memory usage is high
4. Check for additional resource leaks in custom extensions

### If new errors appear:
1. Review the error logs
2. Check if error patterns match known issues
3. Consider adjusting timeout values
4. Verify proper cleanup in custom code

## Support

- Review the WORKER_EXHAUSTION_FIXES.md for detailed explanation
- Run diagnostics.py for system health status
- Monitor logs for resource usage patterns
- Check resource_config.py for tunable parameters
