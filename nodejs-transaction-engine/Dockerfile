FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install --only=production

COPY src/ ./src/
COPY ecosystem.config.js .

RUN mkdir logs

EXPOSE 3000

CMD ["npm", "run", "pm2"]