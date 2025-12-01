package com.example.complexdemo;

import java.util.*;
import java.util.stream.Collectors;
import java.io.Serializable;

// Custom annotation
@interface Audit {
    String value();
}

// Enum with fields and methods
enum Status {
    ACTIVE("A"), INACTIVE("I"), PENDING("P");
    private final String code;
    Status(String code) { this.code = code; }
    public String getCode() { return code; }
}

// Interface with generics
interface Repository<T, ID> {
    void save(T entity);
    Optional<T> findById(ID id);
}

// Abstract class
abstract class BaseEntity implements Serializable {
    private static final long serialVersionUID = 1L;
    protected UUID id = UUID.randomUUID();
    public UUID getId() { return id; }
    public abstract String describe();
}

// Main class with inner classes, static block, and generics
@Audit("MainEntity")
public class ChronicleEntity extends BaseEntity implements Comparable<ChronicleEntity> {
    private String title;
    private int version;
    private Status status;
    private static final List<ChronicleEntity> registry = new ArrayList<>();

    // Static block
    static {
        System.out.println("Static initialization block executed!");
    }

    // Constructor
    public ChronicleEntity(String title, int version, Status status) {
        this.title = title;
        this.version = version;
        this.status = status;
        registry.add(this);
    }

    // Inner class
    public class Metadata {
        private String author;
        private String category;
        public Metadata(String author, String category) {
            this.author = author;
            this.category = category;
        }
        public String summary() {
            return author + " - " + category;
        }
    }

    // Static nested class
    public static class Utils {
        public static void printRegistry() {
            registry.forEach(System.out::println);
        }
    }

    // Method overriding
    @Override
    public String describe() {
        return "ChronicleEntity[title=" + title + ", version=" + version + ", status=" + status + "]";
    }

    // Comparable implementation
    @Override
    public int compareTo(ChronicleEntity other) {
        return Integer.compare(this.version, other.version);
    }

    // Generic method
    public <T> List<T> convert(Collection<T> input) {
        return new ArrayList<>(input);
    }

    // Exception handling
    public void riskyOperation() throws Exception {
        if (version < 0) throw new Exception("Version cannot be negative!");
    }

    // Lambda and Streams
    public static List<String> getTitlesOfActive() {
        return registry.stream()
                .filter(e -> e.status == Status.ACTIVE)
                .map(e -> e.title)
                .collect(Collectors.toList());
    }

    // Main method
    public static void main(String[] args) {
        ChronicleEntity e1 = new ChronicleEntity("Alpha", 1, Status.ACTIVE);
        ChronicleEntity e2 = new ChronicleEntity("Beta", -1, Status.PENDING);

        Metadata meta = e1.new Metadata("Subhadeep", "Demo");
        System.out.println("Metadata: " + meta.summary());

        Utils.printRegistry();

        try {
            e2.riskyOperation();
        } catch (Exception ex) {
            System.err.println("Caught exception: " + ex.getMessage());
        }

        System.out.println("Active titles: " + getTitlesOfActive());
    }
}
