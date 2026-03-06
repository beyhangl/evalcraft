.PHONY: dev demo down seed test build logs clean

dev: .env  ## Boot full stack (postgres + redis + backend + frontend)
	docker compose up --build

demo: .env  ## Boot stack, wait for health, then seed demo data
	docker compose up --build -d
	@echo "Waiting for backend to start..."
	@sleep 5
	python scripts/seed_demo.py

down:  ## Stop everything and remove volumes
	docker compose down -v

seed:  ## Seed demo data (backend must be running)
	python scripts/seed_demo.py

test:  ## Run SDK test suite
	cd evalcraft && pytest tests/ -q

build:  ## Build all Docker images
	docker compose build

logs:  ## Tail all container logs
	docker compose logs -f

clean:  ## Stop everything, remove volumes and local images
	docker compose down -v --rmi local

.env:  ## Create .env from example if missing
	cp .env.example .env
	@echo "Created .env from .env.example — edit as needed."
