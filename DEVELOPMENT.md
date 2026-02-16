# Development Guide

## Development Workflow

### Starting Development

1. **Start Backend** (Terminal 1):
```bash
cd backend
source venv/bin/activate  # Windows: venv\Scripts\activate
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

2. **Start Frontend** (Terminal 2):
```bash
cd frontend
npm run dev
```

3. **Access Applications**:
   - Frontend: http://localhost:3000
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

### Environment Variables

#### Backend (`.env`)
```env
SPOTIFY_CLIENT_ID=your_client_id
SPOTIFY_CLIENT_SECRET=your_client_secret
SPOTIFY_REDIRECT_URI=http://localhost:3000/callback
GOOGLE_CLIENT_ID=your_google_client_id
SECRET_KEY=your_secret_key_for_jwt
DATABASE_URL=sqlite+aiosqlite:///./memorymix.db
FRONTEND_URL=http://localhost:3000
```

#### Frontend (`.env.local`)
```env
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_SPOTIFY_CLIENT_ID=your_spotify_client_id
NEXT_PUBLIC_GOOGLE_CLIENT_ID=your_google_client_id
```

## Code Structure

### Backend Architecture

```
backend/
├── main.py                   # App initialization, CORS, routers
├── config.py                 # Pydantic Settings
├── database.py               # SQLAlchemy async setup
├── models.py                 # Database models
├── schemas.py                # Request/response schemas
├── auth.py                   # JWT + OAuth utilities
├── routers/
│   ├── auth.py              # /auth endpoints
│   ├── spotify.py           # /spotify endpoints
│   ├── memories.py          # /memories endpoints
│   └── mappings.py          # /mappings endpoints
└── services/
    ├── spotify_service.py   # Spotify API logic
    └── matching_service.py  # Matching algorithm
```

### Frontend Architecture

```
frontend/
├── app/
│   ├── layout.tsx           # Root layout with providers
│   ├── page.tsx             # Landing page
│   ├── callback/            # OAuth callback
│   ├── dashboard/           # Main dashboard
│   └── memories/            # Memory pages
│       ├── new/             # Create memory
│       └── [id]/            # Memory detail
├── components/
│   └── Providers.tsx        # React Query + Auth
├── contexts/
│   └── AuthContext.tsx      # Auth state
└── lib/
    ├── api-client.ts        # API wrapper
    └── types.ts             # TypeScript types
```

## Adding New Features

### Adding a Backend Endpoint

1. **Create Schema** in `schemas.py`:
```python
class NewFeatureRequest(BaseModel):
    field: str

class NewFeatureResponse(BaseModel):
    id: int
    field: str
```

2. **Add Router** in `routers/`:
```python
@router.post("/endpoint", response_model=NewFeatureResponse)
async def create_feature(
    data: NewFeatureRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user)
):
    # Implementation
    pass
```

3. **Include Router** in `main.py`:
```python
from routers import new_feature
app.include_router(new_feature.router)
```

### Adding a Frontend Page

1. **Create Page** in `app/new-page/page.tsx`:
```tsx
'use client';

export default function NewPage() {
  return <div>New Page</div>;
}
```

2. **Add API Call** in `lib/api-client.ts`:
```typescript
async newFeature(data: any) {
  const { data: result } = await this.client.post('/endpoint', data);
  return result;
}
```

3. **Use in Component**:
```tsx
import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';

const { data } = useQuery({
  queryKey: ['feature'],
  queryFn: () => apiClient.newFeature({}),
});
```

## Database Migrations

### Using Alembic (Optional)

1. **Install Alembic**:
```bash
pip install alembic
```

2. **Initialize**:
```bash
alembic init alembic
```

3. **Create Migration**:
```bash
alembic revision --autogenerate -m "description"
```

4. **Apply Migration**:
```bash
alembic upgrade head
```

### Manual Schema Updates

Currently using `Base.metadata.create_all()` in `database.py`.
For production, consider implementing proper migrations.

## Testing

### Backend Testing

1. **Install pytest**:
```bash
pip install pytest pytest-asyncio httpx
```

2. **Create test file** `tests/test_api.py`:
```python
import pytest
from httpx import AsyncClient
from main import app

@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
```

3. **Run tests**:
```bash
pytest
```

### Frontend Testing

1. **Install testing libraries**:
```bash
npm install --save-dev @testing-library/react @testing-library/jest-dom jest
```

2. **Create test** `__tests__/page.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react';
import Home from '@/app/page';

test('renders landing page', () => {
  render(<Home />);
  expect(screen.getByText('Memory Mix')).toBeInTheDocument();
});
```

## Debugging

### Backend Debugging

1. **Add print statements**:
```python
print(f"Debug: {variable}")
```

2. **Use Python debugger**:
```python
import pdb; pdb.set_trace()
```

3. **Check logs** in terminal running uvicorn

### Frontend Debugging

1. **Browser DevTools** (F12)
2. **Console logs**:
```typescript
console.log('Debug:', variable);
```

3. **React DevTools** extension
4. **Network tab** for API calls

## Common Tasks

### Reset Database

```bash
cd backend
rm memorymix.db
# Restart backend to recreate
```

### Clear Auth Token

```javascript
// In browser console
localStorage.removeItem('token');
```

### Sync Fresh Spotify Data

1. Login to app
2. Go to Dashboard
3. Click "Sync Spotify History"

### Update Dependencies

**Backend:**
```bash
pip list --outdated
pip install --upgrade package_name
pip freeze > requirements.txt
```

**Frontend:**
```bash
npm outdated
npm update
```

## Performance Tips

### Backend
- Use async/await consistently
- Index frequently queried fields
- Implement caching for Spotify API calls
- Use connection pooling for database

### Frontend
- Use React Query caching effectively
- Implement virtual scrolling for large lists
- Lazy load images
- Minimize bundle size

## Deployment

### Backend (Production)

1. **Use PostgreSQL** instead of SQLite:
```python
DATABASE_URL=postgresql+asyncpg://user:pass@host/db
```

2. **Use Gunicorn** with Uvicorn workers:
```bash
gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker
```

3. **Set production environment variables**

### Frontend (Production)

1. **Build**:
```bash
npm run build
```

2. **Start**:
```bash
npm start
```

3. **Deploy to Vercel**:
```bash
vercel deploy
```

## Security Checklist

- [ ] Use environment variables for secrets
- [ ] Implement rate limiting
- [ ] Validate all user inputs
- [ ] Use HTTPS in production
- [ ] Implement CSRF protection
- [ ] Set secure cookie flags
- [ ] Regular dependency updates
- [ ] SQL injection prevention (ORM helps)

## Git Workflow

```bash
# Create feature branch
git checkout -b feature/new-feature

# Make changes and commit
git add .
git commit -m "Add new feature"

# Push to remote
git push origin feature/new-feature

# Create pull request on GitHub
```

## Useful Commands

### Backend
```bash
# Format code
black .

# Type checking
mypy .

# Linting
flake8 .
```

### Frontend
```bash
# Format code
npm run format

# Type checking
npm run type-check

# Linting
npm run lint
```

## Resources

- [FastAPI Docs](https://fastapi.tiangolo.com/)
- [Next.js Docs](https://nextjs.org/docs)
- [Spotify Web API](https://developer.spotify.com/documentation/web-api)
- [Google Picker API](https://developers.google.com/picker)
- [React Query Docs](https://tanstack.com/query/latest)
- [Tailwind CSS](https://tailwindcss.com/docs)
