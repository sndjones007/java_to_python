// File: Person.java
package com.example.demo;

// Multiple imports from different packages
import java.util.Objects;          // Utility for null checks
import java.time.LocalDate;        // Date handling
import java.time.Period;           // For calculating age difference
import java.util.Random;           // For generating random IDs

public class Person {

    // Fields
    private final String name;   // final field
    private int age;             // mutable field
    private final int id;        // random unique ID

    // Constructor with parameters
    public Person(String name, int age) {
        this.name = Objects.requireNonNull(name, "Name cannot be null");
        this.age = age;
        this.id = new Random().nextInt(1000); // random ID between 0–999
    }

    // Empty method
    public void greet() {
        // Intentionally left empty
    }

    // Method with multiple parameters
    public void updateDetails(int newAge, LocalDate birthDate) {
        this.age = newAge;
        Period p = Period.between(birthDate, LocalDate.now());
        System.out.println(name + " updated age to " + newAge + " (calculated years: " + p.getYears() + ")");
    }

    // Getter method
    public int getAge() {
        return age;
    }

    // Display info method
    public void displayInfo() {
        System.out.println("ID: " + id + ", Name: " + name + ", Age: " + age);
    }
}
