module.exports = {
    apps: [{
      name: 'roku-trade-engine',
      script: 'src/index.js',
      instances: 1,
      exec_mode: 'cluster',
      max_memory_restart: '1G',
      error_file: './logs/err.log',
      out_file: './logs/out.log',
      log_file: './logs/combined.log',
      time: true,
      env: {
        NODE_ENV: 'production'
      }
    }]
  };