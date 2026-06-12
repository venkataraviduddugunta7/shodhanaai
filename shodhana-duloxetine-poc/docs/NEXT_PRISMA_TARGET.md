# Next.js + Prisma Target

The current POC is intentionally runnable without installs. Production can move to this stack:

- Frontend: Next.js + TypeScript + Tailwind CSS
- Backend: Next.js API routes
- Database: PostgreSQL
- ORM: Prisma
- Excel parsing: `xlsx` package or Python pandas service
- Charts: Recharts
- AI: OpenAI or AWS Bedrock service layer

## Migration Steps

1. Create Next.js app after npm/node tooling is installed.
2. Move product/company/unit cleaning functions from `backend/normalization.py` into TypeScript services or expose them through a Python worker.
3. Use the schema in `prisma/schema.prisma`.
4. Replace SQLite persistence with PostgreSQL.
5. Replace current HTML screens with Next pages:
   - `/upload`
   - `/cleaning-summary`
   - `/dashboard`
   - `/opportunities`
   - `/mappings/products`
   - `/mappings/companies`
   - `/pitch/[opportunityId]`
6. Replace mocked `backend/ai_service.py` with a real AI provider.
7. Add login, approval workflow, and audit history before any external email automation.

## Product Rule

Do not start with generic chatbot behavior. Keep the model grounded in uploaded trade rows, approved mappings, and verified Shodhana knowledge.

