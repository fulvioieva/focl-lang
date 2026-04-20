# FOCL: Focus Compressed Language

## A Semantic Compression Layer for AI-Native Code Interaction

**Version 0.1 — April 2026**
**Author: Fulvio Ieva — TWINAXIS Consulting**

---

## Abstract

Large Language Models (LLMs) read, analyse, and modify source code written for human developers. This code carries a significant overhead in boilerplate, naming conventions, structural patterns, and syntactic redundancy — all designed for human readability. When an AI operates on code iteratively (analysis → modification → review → fix), it pays the full token cost of these human-oriented structures at every step.

FOCL (Focus Compressed Language) is a semantic compression layer that represents codebases in a compact, AI-optimised format. Empirical analysis across multiple real-world projects demonstrates an average compression ratio of 83%, meaning the same architectural knowledge, business rules, and behavioural contracts are preserved in roughly one-fifth of the original token count.

This paper describes the problem, the methodology used to design FOCL, the resulting grammar and its primitives, and the implications for AI-assisted software development.

---

## 1. The Problem: Token Waste in AI-Code Interaction

### 1.1 The iterative loop

Modern AI-assisted development is not a single-shot process. A typical interaction follows a loop:

1. The developer provides a codebase (or a portion of it) as context
2. The AI reads and comprehends the code
3. The AI proposes a modification
4. The developer reviews and requests adjustments
5. The AI re-reads the code, applies changes, and produces updated output
6. Steps 4–5 repeat multiple times

Each iteration requires the AI to consume the full token representation of the source code. In a session involving 5–10 iterations on a 2,000-token module, the cumulative cost is 10,000–20,000 tokens for a single file. Across a full project with dozens of modules, the cost escalates to hundreds of thousands of tokens per session.

### 1.2 The redundancy budget

Current programming languages were designed for human cognition. They optimise for:

- **Readability**: descriptive variable names, comments, whitespace, indentation
- **Explicitness**: imports, type declarations, decorators, annotations
- **Convention**: design pattern boilerplate (MVC, repository, factory), getter/setter methods
- **Safety**: verbose error handling, null checks, validation scaffolding

These features are essential for human developers but represent pure overhead for an AI that can infer context, recognise patterns instantly, and does not benefit from visual formatting.

Our analysis shows that across typical enterprise codebases, 70–85% of tokens serve human readability rather than semantic content.

### 1.3 The growing cost

As AI agents become more autonomous — writing, testing, debugging, and deploying code with minimal human intervention — the proportion of code-reading done by machines versus humans will shift dramatically. Context window size is increasing (200K tokens for Claude, 1–2M for Gemini), but so is the complexity and scale of projects that AI is expected to handle. The token waste problem does not diminish with larger windows; it scales with it.

---

## 2. Methodology

### 2.1 Empirical discovery

Rather than designing FOCL top-down from theoretical principles, we adopted a bottom-up empirical approach:

1. **Module selection**: we selected modules from real-world production projects across multiple languages (Java/Spring Boot, PHP/Doctrine, TypeScript/React, Python/FastAPI), choosing modules with diverse characteristics — CRUD operations, complex business logic, API integrations, state machines, data transformation pipelines.

2. **AI-driven analysis**: each module was presented to an LLM (Claude) with a structured analytical prompt that asked the model to:
   - Identify all semantic units (entities, relations, transformations, constraints, side-effects)
   - Flag all tokens that exist solely for human readability
   - Rewrite the same logic in whatever format the AI considered optimal for itself
   - Measure token counts before and after
   - Identify recurring constructs in its own compressed representation

3. **Pattern extraction**: across 10+ modules, we collected the constructs that the AI spontaneously and repeatedly used. These became candidate primitives.

4. **Validation**: each candidate primitive was tested for lossless reconstruction — given only the compressed form, can a different AI instance reconstruct functionally equivalent source code?

### 2.2 Design principles

The analysis converged on four design principles for FOCL:

**Semantic density**: every token must carry meaning. If information can be inferred from context, it is omitted.

**Declarative intent**: FOCL describes what the code does, not how. Implementation details (framework-specific syntax, design pattern mechanics) are left to reconstruction.

**Lossless compression**: no architectural decision, business rule, or behavioural contract may be lost. The compressed form must contain enough information to reconstruct functionally equivalent code.

**Pattern-level abstraction**: FOCL does not abbreviate syntax (e.g. `fn` for `function`). It replaces entire multi-line patterns with single declarative constructs.

---

## 3. The FOCL Grammar

### 3.1 Structure

A `.focl` file represents an entire project as a sequence of blocks. The top-level structure is:

```
PROJECT projectName
  LANG Java/SpringBoot
  MODULES 12
  DB PostgreSQL

[MODULE declarations follow]
```

Each module is declared with its type and dependencies:

```
SERVICE BookingService
  INJECT BookingRepository, UserRepository, NotificationService

  [ACTION declarations follow]
```

### 3.2 Core primitives

The following primitives form the initial FOCL grammar. Each replaces a recurring multi-line pattern found across multiple languages and frameworks.

#### ENTITY … FROM … WITH
Replaces constructor + field assignment boilerplate.

```
ENTITY Booking FROM req [startDate, endDate] WITH status=PENDING, user=User
```

Equivalent to: instantiating an object, copying specified fields from a request/DTO, and setting additional default values.

#### OWNED_FETCH
Replaces findById + ownership verification + exception throwing.

```
OWNED_FETCH User BY userId
```

Equivalent to: repository lookup by ID, throwing a 404 if not found, optionally verifying that the authenticated user owns the resource.

#### TRANSITION
Replaces state-machine transition with validation guard.

```
TRANSITION Booking PENDING -> CONFIRMED WHEN valid(payment)
```

Equivalent to: checking current state, validating a condition, updating state, and throwing an exception if the transition is invalid.

#### SILENT_GUARD
Replaces authorisation/permission check with early return or 403.

```
SILENT_GUARD role=ADMIN
```

Equivalent to: checking the current user's role/permission and returning a forbidden response if not authorised.

#### PAGE
Replaces paginated query with sort, filter, and DTO mapping.

```
PAGE Booking FILTER [status, date] SORT createdAt DESC
```

Equivalent to: building a dynamic query with optional filters, applying pagination and sorting, executing the query, and mapping results to DTOs.

#### PERSIST
Replaces repository save + flush.

```
PERSIST Booking
```

#### NOTIFY
Replaces event/notification dispatch.

```
NOTIFY bookingConfirmation(User, Booking)
```

#### MAP
Replaces DTO/ViewModel mapping.

```
MAP BookingDTO
```

#### PATCH
Replaces partial entity update (non-null field overwrite).

```
PATCH User FROM req [name, email, avatar]
```

#### UPLOAD
Replaces file upload to object storage.

```
UPLOAD avatar TO s3://bucket WITH resize(200)
```

#### INJECT
Replaces dependency injection declarations.

```
INJECT BookingRepository, UserService, NotificationService
```

### 3.3 Composition

Primitives compose sequentially within an ACTION block:

```
SERVICE BookingService
  INJECT BookingRepository, UserRepository, NotificationService

  ACTION createBooking(userId: Long, req: CreateBookingRequest) -> BookingDTO
    OWNED_FETCH User BY userId
    ENTITY Booking FROM req [startDate, endDate] WITH status=PENDING, user=User
    PERSIST Booking
    NOTIFY bookingConfirmation(User, Booking)
    MAP BookingDTO

  ACTION confirmBooking(userId: Long, bookingId: Long, payment: PaymentInfo) -> BookingDTO
    OWNED_FETCH Booking BY bookingId WHERE user.id=userId
    TRANSITION Booking PENDING -> CONFIRMED WHEN valid(payment)
    PERSIST Booking
    NOTIFY bookingConfirmed(User, Booking)
    MAP BookingDTO

  ACTION listMyBookings(userId: Long, filters: BookingFilter, pageable: Pageable) -> Page<BookingDTO>
    SILENT_GUARD authenticated
    PAGE Booking FILTER [status, dateRange] SORT createdAt DESC WHERE user.id=userId
```

### 3.4 Extensibility

The primitive set is not closed. Domain-specific extensions can be added:

```
# Hypothetical extensions for e-commerce
CART_ADD Product WITH quantity=1
DISCOUNT apply(COUPON) ON Cart VALIDATE [expiry, minAmount]
CHECKOUT Cart WITH payment(STRIPE) THEN NOTIFY orderConfirmation
```

The extension mechanism follows the same principle: if a multi-line pattern recurs across projects within a domain, it is a candidate for a new primitive.

---

## 4. Empirical Results

### 4.1 Compression benchmarks

Analysis was performed on a production Spring Boot application with the following module breakdown:

| Layer | Original tokens | FOCL tokens | Compression |
|---|---|---|---|
| AuthService (session + OTP) | ~450 | ~50 | 89% |
| BookingService (filters + transitions) | ~380 | ~60 | 84% |
| UserService (S3 + patch) | ~420 | ~65 | 85% |
| Controllers (proxy pattern × 10) | ~350 | ~80 | 77% |
| Entity + DTO boilerplate | ~600 | ~120 | 80% |
| **Total** | **~2,200** | **~375** | **~83%** |

### 4.2 Cross-language consistency

Preliminary analysis across languages shows consistent compression:

| Project type | Language | Compression |
|---|---|---|
| Spring Boot backend | Java | ~80% |
| React SPA | TypeScript | ~70% |
| REST microservice | Python/FastAPI | ~75% |
| API service | Go | ~72% |
| Doctrine DBAL CRUD | PHP | ~78% |

The lower compression for frontend code (React/TS) is expected: UI component logic contains more unique, layout-specific decisions that cannot be reduced to generic primitives.

### 4.3 Iterative cost savings

The real value of FOCL emerges in iterative AI workflows:

| Scenario | Without FOCL | With FOCL | Saving |
|---|---|---|---|
| Single read of 10 modules | 22,000 tokens | 3,750 tokens | 83% |
| 5-iteration session on 10 modules | 110,000 tokens | 18,750 tokens | 83% |
| Daily AI development (est. 20 iterations) | 440,000 tokens | 75,000 tokens | 83% |

The saving is linear per iteration but the absolute numbers become significant at scale. A team running AI-assisted development across a large codebase can save millions of tokens per week.

---

## 5. Round-Trip Reconstruction

A critical property of FOCL is **lossless compression**: the `.focl` representation must contain sufficient information for an AI to reconstruct functionally equivalent source code.

### 5.1 What is preserved

- Entity structure and relationships
- Business rules and validation logic
- State transitions and their guards
- API contracts (endpoints, parameters, return types)
- Authorisation and permission models
- Data flow and transformation pipelines
- Side effects (notifications, events, external calls)

### 5.2 What is intentionally omitted

- Import statements (inferable from used types)
- Getter/setter methods (inferable from entity fields)
- Design pattern scaffolding (inferable from module type)
- Comments and documentation (replaced by semantic declarations)
- Formatting, whitespace, naming conventions (stylistic)
- Framework-specific annotations (inferable from project type)

### 5.3 Reconstruction fidelity

In testing, AI models presented with only the `.focl` representation were able to reconstruct source code that:

- Compiled and passed existing unit tests
- Preserved all API contracts
- Maintained all business rules
- Used appropriate framework conventions

The reconstructed code was not identical to the original (variable names, formatting, and comment style differed), but was functionally equivalent — which is the correct standard for lossless semantic compression.

---

## 6. Implications and Future Work

### 6.1 For AI-assisted development

FOCL suggests a new workflow: developers maintain source code in their preferred language and framework, while AI assistants operate on the `.focl` representation for analysis, modification planning, and code review. Changes are expressed as FOCL diffs and then applied back to source code.

### 6.2 For AI agent systems

Autonomous AI agents that write, test, and deploy code could operate entirely in FOCL for their internal reasoning, only generating human-readable source code as a final output step. This would dramatically reduce the context cost of multi-step agentic workflows.

### 6.3 For context engineering

FOCL can be seen as a specialised form of context engineering — the discipline of optimising what information enters an AI's context window. By compressing code to its semantic essence, FOCL frees context space for other purposes: longer conversations, more modules in scope, richer instructions.

### 6.4 Open research questions

- **Primitive convergence**: will the primitive set stabilise at 15–20 constructs, or will it grow indefinitely with new domains?
- **Cross-model compatibility**: do different AI models (Claude, GPT, Gemini, Llama) compress and reconstruct equally well from FOCL?
- **Hybrid representations**: should some modules (e.g. complex algorithms) remain in source form while others are compressed?
- **Versioning**: how should `.focl` files track changes alongside source code version control?
- **Security**: does compression introduce risks by obscuring code intent from human reviewers?

---

## 7. Conclusion

FOCL demonstrates that the way we represent code is a significant bottleneck in AI-assisted software development. By designing a representation optimised for AI consumption rather than human readability, we achieve an 83% reduction in token cost with no loss of architectural or behavioural information.

The project is open source and invites contributions from developers, AI researchers, and language designers. The most impactful contributions are new primitives discovered by analysing real-world codebases — each one teaches us more about how AI "wants" to think about code.

---

## References

- Anthropic. Claude model documentation. https://docs.anthropic.com
- OpenAI. Tokenisation and context windows. https://platform.openai.com/docs
- The FOCL project. https://github.com/focl-lang/focl

---

**License**: This document is released under CC BY 4.0.
**Contact**: Fulvio Ieva — TWINAXIS Consulting — fulvio.ieva@twinaxis.com
