FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install --only=production

COPY src/ ./src/

RUN echo 'module.exports = { apps: [{ name: "roku-trade", script: "src/index.js", instances: 1, autorestart: true, watch: false, max_memory_restart: "1G", env: { NODE_ENV: "production" } }] };' > ecosystem.config.js

RUN mkdir logs

EXPOSE 3000

CMD ["npm", "run", "pm2"]