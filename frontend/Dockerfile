# Get deps
FROM node:14-alpine AS deps
WORKDIR /deps
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile

# Build the Next.js app
FROM node:14-alpine AS builder
WORKDIR /app
COPY --from=deps /deps/node_modules /app/node_modules
COPY . .
RUN yarn build

# Run the Next.js app
FROM node:14-alpine AS runner
WORKDIR /app
COPY --from=builder /app/.next /app/.next
COPY --from=builder /app/node_modules /app/node_modules
COPY --from=builder /app/package.json /app/package.json
COPY --from=builder /app/public /app/public
EXPOSE 3000
CMD ["yarn", "start"]
