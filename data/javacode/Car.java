// Sample Java Program with fields, constructors, and methods
public class Car {

    // Static field shared across all Car objects
    public static final String MANUFACTURER = "Generic Motors";

    // Instance fields
    private final String model;   // final: must be initialized in constructor
    private int year;             // mutable field
    private double mileage;       // mutable field

    // Constructor
    public Car(String model, int year) {
        this.model = model;
        this.year = year;
        this.mileage = 0.0; // default mileage
    }

    // Public method to drive the car (updates mileage)
    public void drive(double kilometers) {
        if (kilometers > 0) {
            mileage += kilometers;
            System.out.println(model + " drove " + kilometers + " km.");
        } else {
            System.out.println("Distance must be positive!");
        }
    }

    // Private helper method (used internally)
    private String getAgeCategory() {
        int currentYear = 2025; // hardcoded for demo
        int age = currentYear - year;
        if (age < 3) return "New";
        else if (age < 10) return "Used";
        else return "Classic";
    }

    // Public method to display car info
    public void displayInfo() {
        System.out.println("Manufacturer: " + MANUFACTURER);
        System.out.println("Model: " + model);
        System.out.println("Year: " + year);
        System.out.println("Mileage: " + mileage + " km");
        System.out.println("Category: " + getAgeCategory());
    }

    // Static method (utility)
    public static void showManufacturer() {
        System.out.println("All cars are made by " + MANUFACTURER);
    }

    // Main method to test the class
    public static void main(String[] args) {
        Car car1 = new Car("Sedan", 2022);
        Car car2 = new Car("SUV", 2015);

        Car.showManufacturer(); // static method call

        car1.drive(150.5);
        car2.drive(80);

        car1.displayInfo();
        car2.displayInfo();
    }
}
