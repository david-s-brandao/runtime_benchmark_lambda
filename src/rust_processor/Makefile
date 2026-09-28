build:
	cargo lambda build --release

zip:
	cp target/lambda/processor/bootstrap .
	zip bootstrap.zip bootstrap
	rm bootstrap

deploy: build zip
