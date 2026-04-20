# FOCL — Focus Compressed Language

> LLMs waste 80% of their context window reading code written for humans.
> FOCL fixes that.

AI-native codebase compression. Generate a `.focl` file that represents your entire project in **80% fewer tokens** — keeping all the architecture, business rules, and behaviour an AI assistant needs.

## Before / After

A typical Spring Boot service method:

```java
@Service
public class BookingService {

    @Autowired
    private BookingRepository bookingRepository;
    @Autowired
    private UserRepository userRepository;
    @Autowired
    private NotificationService notificationService;

    @Transactional
    public BookingDTO createBooking(Long userId, CreateBookingRequest req) {
        User user = userRepository.findById(userId)
            .orElseThrow(() -> new ResourceNotFoundException("User not found"));
        Booking booking = new Booking();
        booking.setUser(user);
        booking.setStartDate(req.getStartDate());
        booking.setEndDate(req.getEndDate());
        booking.setStatus(BookingStatus.PENDING);
        Booking saved = bookingRepository.save(booking);
        notificationService.sendBookingConfirmation(user, saved);
        return BookingMapper.toDTO(saved);
    }
}
```

The same logic in FOCL (~85% fewer tokens):

```
SERVICE BookingService
  INJECT BookingRepository, UserRepository, NotificationService

  ACTION createBooking(userId: Long, req: CreateBookingRequest) -> BookingDTO
    OWNED_FETCH User BY userId
    ENTITY Booking FROM req [startDate, endDate] WITH status=PENDING, user=User
    PERSIST Booking
    NOTIFY bookingConfirmation(User, Booking)
    MAP BookingDTO
```

When an AI reads your codebase through FOCL, it consumes a fraction of the tokens — and every iteration (analysis, modification, review) compounds the saving.

## Why

Every time an AI assistant reads, modifies, and rewrites your code, it pays the full token cost of structures designed for human eyes: verbose naming, boilerplate imports, decorators, getters/setters, repetitive patterns.

In a typical development session an AI touches the same code 5–10 times. With a 2,000-token module that means 10,000–20,000 tokens spent on a single file. FOCL compresses that module to ~400 tokens: same information, same iterations, **5× less cost**.

FOCL is not a new programming language to write code in. It is a **semantic compression layer** — a compact representation that AI models read and manipulate natively, while your original source code stays untouched.

## Install

```bash
pip install -e .
```

Set your Anthropic API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

## Commands

### `focl init [path]`
Analyse a codebase and generate a `.focl` file.

```bash
focl init .
focl init /path/to/project --output myapp.focl
```

### `focl watch [path]`
Watch for source changes and automatically patch the `.focl` file.

```bash
focl watch .
focl watch . --debounce 5
```

### `focl sync [path]`
Full re-generation of the `.focl` file from scratch.

```bash
focl sync .
```

### `focl stats [path]`
Show compression statistics.

```bash
focl stats .
```

## How it works

1. **Detect** — scans the project to identify language and framework (Java/Spring Boot, TypeScript/React, Python, Go, …)
2. **Collect** — gathers all source files, skipping binaries, build artifacts, and `node_modules`
3. **Compress** — sends the codebase to Claude with the FOCL grammar, applying semantic primitives to each module
4. **Save** — writes the `.focl` file next to your code
5. **Watch** — detects file changes and calls Claude to patch only the affected FOCL blocks

## FOCL primitives

The grammar is built around a compact set of semantic primitives. Each one replaces a recurring multi-line pattern with a single declarative construct.

| Primitive | Replaces | Example |
|-----------|----------|---------|
| `ENTITY … FROM … WITH` | Constructor + field assignment boilerplate | `ENTITY Booking FROM req [start, end] WITH status=PENDING` |
| `OWNED_FETCH` | findById + ownership check + 404 exception | `OWNED_FETCH User BY userId` |
| `TRANSITION` | State-machine transition + validation guard | `TRANSITION Booking PENDING -> CONFIRMED WHEN valid(payment)` |
| `SILENT_GUARD` | Auth/permission check + 403 early return | `SILENT_GUARD role=ADMIN` |
| `PAGE` | Paginated query + sort + filter + DTO mapping | `PAGE Booking FILTER [status, date] SORT createdAt DESC` |
| `PERSIST` | Repository save + flush | `PERSIST Booking` |
| `NOTIFY` | Event/notification dispatch | `NOTIFY bookingConfirmation(User, Booking)` |
| `MAP` | DTO/ViewModel mapping | `MAP BookingDTO` |
| `INJECT` | Dependency injection declarations | `INJECT BookingRepository, UserService` |
| `PATCH` | Partial entity update (non-null fields only) | `PATCH User FROM req [name, email, avatar]` |
| `UPLOAD` | File upload to object storage | `UPLOAD avatar TO s3://bucket WITH resize(200)` |

> This is the initial set. Primitives evolve as more codebases are analysed — contributions welcome.

## Supported languages

Java · Kotlin · TypeScript · JavaScript · Python · Go · Ruby · PHP · C#

## Token savings

| Project type | Typical saving |
|---|---|
| Spring Boot backend | ~80% |
| React/TS frontend | ~70% |
| Python microservice | ~75% |
| Go service | ~72% |

Measured by comparing `tiktoken` counts of original source files vs. the generated `.focl` representation.

## Roadmap

- [x] Core grammar and primitives
- [x] `focl init` — full codebase analysis
- [x] `focl watch` — incremental patching
- [ ] `focl decompile` — reconstruct source from `.focl` (round-trip)
- [ ] IDE extension (VS Code) — side-by-side `.focl` view
- [ ] Multi-model support (GPT, Gemini, Llama)
- [ ] Plugin system for domain-specific primitive packs
- [ ] Benchmark suite for cross-language compression metrics

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Key areas where help is needed:
- **New primitives** — analyse your own codebases, discover recurring patterns, propose new constructs
- **Language support** — extend detection and compression for additional languages/frameworks
- **Benchmarks** — run `focl stats` on real projects and share anonymised results
- **Documentation** — examples, tutorials, case studies

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.

---

**FOCL** is a project by [Fulvio Ieva](https://github.com/fulvioieva) / TWINAXIS Consulting.
