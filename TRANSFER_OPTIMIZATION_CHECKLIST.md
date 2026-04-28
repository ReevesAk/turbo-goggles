# Transfer Endpoint Profiling & Optimization Checklist

## 1. Profile the Endpoint
- [ ] Use Django Debug Toolbar to profile transfer API requests
- [ ] Identify slow DB queries (look for N+1, missing indexes)
- [ ] Time external API calls (wallet, bank, etc.)
- [ ] Measure serialization/deserialization time
- [ ] Check Celery task queue/latency

## 2. Optimize Database Access
- [ ] Use `select_related`/`prefetch_related` for related models
- [ ] Add indexes to frequently queried fields (account, tx id)
- [ ] Use transactions for atomic operations
- [ ] Batch DB operations if possible

## 3. Offload Non-Critical Tasks
- [ ] Move notifications, logging, and analytics to Celery
- [ ] Use dedicated Celery queues for high-priority tasks

## 4. Improve External API Performance
- [ ] Use async HTTP clients if possible
- [ ] Implement retries with backoff for flaky endpoints
- [ ] Cache static/slow-changing data

## 5. Tune Celery & Infrastructure
- [ ] Increase Celery worker concurrency
- [ ] Use connection pooling for DB/Redis
- [ ] Monitor worker queue length and task duration

## 6. Code Refactoring
- [ ] Refactor hot paths for efficiency
- [ ] Minimize data passed between layers
- [ ] Avoid unnecessary serialization

## 7. Monitor & Iterate
- [ ] Set up monitoring for transfer latency
- [ ] Log slow requests and investigate
- [ ] Continuously profile and optimize

---

**Tip:** Start by profiling a single transfer request and address the slowest step first. Repeat until performance is satisfactory.
