window.AgixtCrudExtension.register({
  id: 'admin-notifications',
  label: 'System Notifications',
  singular: 'notification',
  endpoint: '/v1/notifications/system?include_expired=true',
  listKey: 'notifications',
  createLabel: 'New notification',
  update: false,
  delete: false,
  searchKeys: ['title', 'message', 'notification_type', 'created_by_email'],
  columns: [
    { key: 'title', label: 'Title' },
    { key: 'notification_type', label: 'Type', format: 'status' },
    { key: 'created_by_email', label: 'Created By' },
    { key: 'created_at', label: 'Created', format: 'datetime' },
    { key: 'expires_at', label: 'Expires', format: 'datetime' },
    { key: 'is_active', label: 'Active', format: 'bool' },
  ],
  summary: [
    { label: 'Active', value: (rows) => rows.filter((r) => r.is_active).length, tone: 'good' },
    { label: 'Critical', value: (rows) => rows.filter((r) => r.notification_type === 'critical').length, tone: 'bad' },
    { label: 'Warnings', value: (rows) => rows.filter((r) => r.notification_type === 'warning').length, tone: 'warn' },
  ],
  fields: [
    { key: 'title', label: 'Title', required: true },
    { key: 'message', label: 'Message', type: 'textarea', rows: 5, required: true },
    { key: 'notification_type', label: 'Type', type: 'select', value: 'info', options: ['info', 'warning', 'critical'] },
    { key: 'expires_in_minutes', label: 'Expires in minutes', type: 'number', required: true, value: 60 },
  ],
  actions: [
    { id: 'deactivate', label: 'Deactivate', method: 'POST', path: '/v1/notifications/system/{id}/deactivate', confirm: 'Deactivate this notification?', danger: true },
  ],
});
